# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PsrDeliveryNote(models.Model):
    _name = 'psr.delivery.note'
    _description = 'Delivery / Unloading Note'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'unloading_date desc, id desc'

    name = fields.Char(string='Delivery Note No.', required=True, copy=False,
                        default=lambda self: _('New'), tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('unloaded', 'Unloaded'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', tracking=True)

    gr_id = fields.Many2one('psr.goods.receipt', string='Goods Receipt', required=True, tracking=True)
    trip_sheet_id = fields.Many2one(related='gr_id.trip_sheet_id', string='Trip Sheet', store=True)
    consignee_id = fields.Many2one(related='gr_id.consignee_id', string='Consignee', store=True)

    unloading_location = fields.Char(string='Unloading Location (Godown)')
    unloading_date = fields.Datetime(string='Unloading Date', default=fields.Datetime.now)
    received_by = fields.Char(string='Received By')

    # Additional charges at unloading
    fuel_charges = fields.Monetary(string='GR-Linked Fuel Charges', currency_field='currency_id')
    local_delivery_charges = fields.Monetary(string='Extra / Local Delivery Charges', currency_field='currency_id')
    total_unloading_charges = fields.Monetary(string='Total Charges', currency_field='currency_id',
                                               compute='_compute_total_charges', store=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # Money receipt / payment acknowledgment
    money_receipt_number = fields.Char(string='Money Receipt No.')
    amount_received = fields.Monetary(string='Amount Received', currency_field='currency_id')
    payment_state = fields.Selection([
        ('pending', 'Pending'),
        ('partial', 'Partially Received'),
        ('paid', 'Fully Received'),
    ], string='Payment Status', default='pending', compute='_compute_payment_state', store=True)

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('fuel_charges', 'local_delivery_charges')
    def _compute_total_charges(self):
        for note in self:
            note.total_unloading_charges = note.fuel_charges + note.local_delivery_charges

    @api.depends('amount_received', 'total_unloading_charges')
    def _compute_payment_state(self):
        for note in self:
            if note.amount_received <= 0:
                note.payment_state = 'pending'
            elif note.amount_received < note.total_unloading_charges:
                note.payment_state = 'partial'
            else:
                note.payment_state = 'paid'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('psr.delivery.note') or _('New')
        return super().create(vals_list)

    def action_confirm_unloading(self):
        self.write({'state': 'unloaded'})
        for note in self:
            note.gr_id.action_mark_delivered()

    def action_close(self):
        self.write({'state': 'closed'})
