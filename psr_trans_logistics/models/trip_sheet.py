# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PsrTripSheet(models.Model):
    _name = 'psr.trip.sheet'
    _description = 'Trip Sheet (Transportation Administration)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'trip_date_start desc, id desc'

    name = fields.Char(string='Trip Sheet No.', required=True, copy=False,
                        default=lambda self: _('New'), tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ], string='Status', default='draft', tracking=True)

    # Standard Fleet app - vanilla-based, no re-implementation of vehicle master
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle', required=True, tracking=True)
    driver_id = fields.Many2one('res.partner', string='Driver',
                                 related='vehicle_id.driver_id', store=True, readonly=False)

    origin_location = fields.Char(string='Origin / Start Point')
    destination_location = fields.Char(string='Destination')
    trip_date_start = fields.Datetime(string='Trip Start', default=fields.Datetime.now)
    trip_date_end = fields.Datetime(string='Trip End')

    odometer_start = fields.Float(string='Odometer Start (km)')
    odometer_end = fields.Float(string='Odometer End (km)')
    distance_travelled = fields.Float(string='Distance Travelled (km)',
                                       compute='_compute_distance', store=True)

    # Goods movement for this trip - consolidation across GRs / locations
    gr_ids = fields.Many2many('psr.goods.receipt', string='Consolidated GRs',
                               help='All Goods Receipts consolidated into this trip across booking locations')
    gr_count = fields.Integer(string='GR Count', compute='_compute_gr_count')

    # Fuel consumption - reuses standard Fleet fuel log
    fuel_quantity = fields.Float(string='Fuel Consumed (litres)')
    fuel_cost = fields.Monetary(string='Fuel Cost', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    fuel_log_id = fields.Many2one('fleet.vehicle.log.services', string='Fleet Service/Fuel Log',
                                   copy=False, readonly=True)

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('odometer_start', 'odometer_end')
    def _compute_distance(self):
        for trip in self:
            trip.distance_travelled = max(trip.odometer_end - trip.odometer_start, 0.0)

    @api.depends('gr_ids')
    def _compute_gr_count(self):
        for trip in self:
            trip.gr_count = len(trip.gr_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('psr.trip.sheet') or _('New')
        return super().create(vals_list)

    def action_start_trip(self):
        self.write({'state': 'in_progress'})
        self.gr_ids.write({'state': 'in_transit'})
        for trip in self:
            trip.gr_ids.write({'trip_sheet_id': trip.id})

    def action_complete_trip(self):
        for trip in self:
            if not trip.trip_date_end:
                trip.trip_date_end = fields.Datetime.now()
            if trip.fuel_quantity and not trip.fuel_log_id:
                trip._create_fleet_fuel_log()
        self.write({'state': 'completed'})

    def _create_fleet_fuel_log(self):
        """Push fuel consumption into the standard Fleet app Services log, keeping
        garage / fuel history centralized instead of duplicating it here.
        Odoo 19's Fleet app tracks fuel as a Service record (Service Type = Fuel),
        there is no separate fleet.vehicle.log.fuel model anymore."""
        self.ensure_one()
        if not self.vehicle_id:
            raise UserError(_('Assign a vehicle before logging fuel consumption.'))
        fuel_service_type = self.env['fleet.service.type'].search([('name', '=', 'Fuel')], limit=1)
        if not fuel_service_type:
            fuel_service_type = self.env['fleet.service.type'].create({'name': 'Fuel'})
        fuel_log = self.env['fleet.vehicle.log.services'].create({
            'vehicle_id': self.vehicle_id.id,
            'date': fields.Date.context_today(self),
            'service_type_id': fuel_service_type.id,
            'amount': self.fuel_cost,
            'description': _('Fuel consumption (%(qty)s L) auto-logged from Trip Sheet %(trip)s') % {
                'qty': self.fuel_quantity, 'trip': self.name},
        })
        self.fuel_log_id = fuel_log.id
        return fuel_log
