# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PsrGoodsReceipt(models.Model):
    _name = 'psr.goods.receipt'
    _description = 'Goods Receipt (GR)'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'psr.ai.extraction.mixin']
    _order = 'dispatch_date desc, id desc'

    name = fields.Char(string='GR Number', required=True, copy=False,
                        default=lambda self: _('New'), tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('booked', 'Booked'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Booking / origin
    booking_location = fields.Char(string='Booking / Origin Location', required=True,
                                    help='Station where the consignment was first booked, '
                                         'e.g. Delhi, Ghaziabad, Gujarat, UP, East India, Bihar')
    dispatch_date = fields.Date(string='Date of Dispatch', default=fields.Date.context_today)

    # Parties
    consignor_id = fields.Many2one('res.partner', string='Consignor (Sender)', required=True, tracking=True)
    consignee_id = fields.Many2one('res.partner', string='Consignee (Receiver)', required=True, tracking=True)
    delivery_address_id = fields.Many2one('res.partner', string='Customer Delivery Address',
                                           help='Final delivery address, may differ from the consignee itself '
                                                '(e.g. a specific godown/branch address)')

    # E-way bill
    eway_bill_number = fields.Char(string='E-Way Bill Number')
    eway_bill_date = fields.Date(string='E-Way Bill Date')

    # Packages
    package_count = fields.Integer(string='Number of Packages', default=1)
    is_partial_booking = fields.Boolean(string='Partial Booking',
                                         help='Tick if this GR represents a partial booking of a larger consignment')
    parent_gr_id = fields.Many2one('psr.goods.receipt', string='Parent Consignment',
                                    help='Original GR this partial booking belongs to')

    # Lines - product wise pricing / UOM / volumetric weight
    line_ids = fields.One2many('psr.goods.receipt.line', 'gr_id', string='Product Lines')

    goods_value = fields.Monetary(string='Goods Value', currency_field='currency_id',
                                   compute='_compute_amounts', store=True)
    total_value = fields.Monetary(string='Total Value', currency_field='currency_id',
                                   compute='_compute_amounts', store=True)
    volumetric_weight_total = fields.Float(string='Total Volumetric Weight (kg)',
                                            compute='_compute_amounts', store=True,
                                            help='Sum of volumetric weight across all lines, '
                                                 'used for logistics pricing where volume > actual weight')

    gr_charges = fields.Monetary(string='GR Charges', currency_field='currency_id')
    final_delivery_charges = fields.Monetary(string='Final Delivery Charges', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # Invoice details
    invoice_number = fields.Char(string='Invoice Number')
    invoice_value = fields.Monetary(string='Invoice Value', currency_field='currency_id')
    product_type = fields.Char(string='Product Type')
    payment_terms = fields.Selection([
        ('advance', 'Advance'),
        ('monthly', 'Monthly'),
        ('pay_basis', 'Pay Basis'),
    ], string='Payment Terms', default='pay_basis')
    invoice_id = fields.Many2one('account.move', string='Related Invoice', copy=False)
    
    # Consolidation / trip linkage
    trip_sheet_id = fields.Many2one('psr.trip.sheet', string='Trip Sheet', tracking=True,
                                     help='Trip in which this GR has been consolidated for onward movement')

    # AI-assisted data entry
    source_document = fields.Binary(string='E-Way Bill / Invoice Scan', attachment=True)
    source_document_filename = fields.Char(string='Scan Filename')

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('line_ids.price_subtotal', 'line_ids.volumetric_weight')
    def _compute_amounts(self):
        for gr in self:
            gr.goods_value = sum(gr.line_ids.mapped('price_subtotal'))
            gr.volumetric_weight_total = sum(gr.line_ids.mapped('volumetric_weight'))
            gr.total_value = gr.goods_value + gr.gr_charges + gr.final_delivery_charges

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('psr.goods.receipt') or _('New')
        return super().create(vals_list)

    @api.constrains('package_count')
    def _check_package_count(self):
        for gr in self:
            if gr.package_count <= 0:
                raise ValidationError(_('Number of packages must be greater than zero.'))

    def action_confirm_booking(self):
        self.write({'state': 'booked'})

    def action_mark_in_transit(self):
        self.write({'state': 'in_transit'})

    def action_mark_delivered(self):
        self.write({'state': 'delivered'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})


    def action_print_goods_receipt(self):
        """Called by the 'Print Goods Receipt' header button."""
        self.ensure_one()
        return self.env.ref(
            "psr_trans_logistics.action_report_psr_goods_receipt"
        ).report_action(self)


class PsrGoodsReceiptLine(models.Model):
    _name = 'psr.goods.receipt.line'
    _description = 'Goods Receipt Line (Product-wise pricing & delivery)'
    _order = 'id'

    gr_id = fields.Many2one('psr.goods.receipt', string='GR', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', required=True)
    quantity = fields.Float(string='Quantity', default=1.0)
    rate = fields.Float(string='Rate')
    price_subtotal = fields.Monetary(string='Subtotal', currency_field='currency_id',
                                      compute='_compute_price_subtotal', store=True)
    currency_id = fields.Many2one(related='gr_id.currency_id', store=True)

    # Different delivery address per product line
    delivery_address_id = fields.Many2one('res.partner', string='Delivery Address (this product)')

    # Volumetric weight calculation - standard logistics formula (L x W x H in cm) / 5000 = kg
    length_cm = fields.Float(string='Length (cm)')
    width_cm = fields.Float(string='Width (cm)')
    height_cm = fields.Float(string='Height (cm)')
    volumetric_divisor = fields.Float(string='Volumetric Divisor', default=5000.0,
                                       help='Industry-standard divisor, adjust per carrier agreement')
    volumetric_weight = fields.Float(string='Volumetric Weight (kg)',
                                      compute='_compute_volumetric_weight', store=True)
    actual_weight = fields.Float(string='Actual Weight (kg)')
    chargeable_weight = fields.Float(string='Chargeable Weight (kg)',
                                      compute='_compute_volumetric_weight', store=True,
                                      help='Higher of actual weight and volumetric weight - used for pricing')

    @api.depends('quantity', 'rate')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.rate

    @api.depends('length_cm', 'width_cm', 'height_cm', 'volumetric_divisor', 'quantity', 'actual_weight')
    def _compute_volumetric_weight(self):
        for line in self:
            divisor = line.volumetric_divisor or 5000.0
            per_unit_vw = (line.length_cm * line.width_cm * line.height_cm) / divisor
            line.volumetric_weight = per_unit_vw * (line.quantity or 1.0)
            line.chargeable_weight = max(line.volumetric_weight, line.actual_weight)
