# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class FleetVehicleGms(models.Model):
    """Garage Management extension. Deliberately thin: truck/vehicle master data,
    service history and fuel history already exist in the standard Fleet app.
    We only add spare-parts usage tracking, wired into standard Inventory (stock)
    so stock is actually depleted when a part is consumed - no parallel parts
    database is built."""
    _inherit = 'fleet.vehicle'

    part_usage_ids = fields.One2many('psr.vehicle.part.usage', 'vehicle_id', string='Spare Parts Used')
    part_usage_count = fields.Integer(string='Parts Used', compute='_compute_part_usage_count')

    @api.depends('part_usage_ids')
    def _compute_part_usage_count(self):
        for vehicle in self:
            vehicle.part_usage_count = len(vehicle.part_usage_ids)


class PsrVehiclePartUsage(models.Model):
    _name = 'psr.vehicle.part.usage'
    _description = 'Vehicle Spare Part Usage (Garage Management)'
    _order = 'date desc, id desc'

    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle', required=True, ondelete='cascade')
    service_log_id = fields.Many2one('fleet.vehicle.log.services', string='Related Service Log',
                                      help='Link to the standard Fleet service record this part was used for')
    product_id = fields.Many2one('product.product', string='Spare Part', required=True,
                                  )
    quantity = fields.Float(string='Quantity Used', default=1.0)
    date = fields.Date(string='Date', default=fields.Date.context_today)
    unit_cost = fields.Float(string='Unit Cost', related='product_id.standard_price', readonly=True)
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    stock_move_id = fields.Many2one('stock.move', string='Stock Move', copy=False, readonly=True,
                                     help='Inventory move created to actually deduct the part from stock')
    warehouse_id = fields.Many2one('stock.warehouse', string='Spare Parts Warehouse',
                                    default=lambda self: self.env['stock.warehouse'].search(
                                        [('company_id', '=', self.env.company.id)], limit=1))

    @api.depends('quantity', 'unit_cost')
    def _compute_total_cost(self):
        for usage in self:
            usage.total_cost = usage.quantity * usage.unit_cost

    def action_consume_from_stock(self):
        """Creates and validates a stock.move so the spare part is deducted from
        inventory through the standard Inventory app - no custom stock ledger."""
        for usage in self:
            if usage.stock_move_id:
                continue
            source_location = usage.warehouse_id.lot_stock_id
            dest_location = self.env.ref('stock.location_production',
                                          raise_if_not_found=False) or source_location
            move = self.env['stock.move'].create({
                'name': _('Spare part used on %s') % usage.vehicle_id.display_name,
                'product_id': usage.product_id.id,
                'product_uom_qty': usage.quantity,
                'product_uom': usage.product_id.uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
            })
            move._action_confirm()
            move._action_assign()
            move.picked = True
            move._action_done()
            usage.stock_move_id = move.id
