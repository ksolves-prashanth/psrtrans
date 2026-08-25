# -*- coding: utf-8 -*-
{
    'name': 'PSR Trans Logistics - Transport Operations',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Goods Receipt, Trip Sheet, Delivery/Unloading and Garage Management '
                'for transport & booking agents',
    'description': """
PSR Trans Logistics - Transport Operations
===========================================
Vanilla-based, configurable extension for transportation / delivery / booking
agents handling multiple consignors, consignees and stations.

Covers:
- Goods Receipt (GR) with product-wise pricing, volumetric weight & e-way bill capture
- Trip Sheet for transportation administration (built on the standard Fleet app)
- Delivery / Unloading with consolidation and money receipt tracking
- Garage Management (GMS) - spare parts usage against the standard Fleet app
- Optional AI-assisted document extraction for GR data entry
    """,
    'author': 'Ksolves India Limited',
    'depends': ['base', 'mail', 'fleet', 'stock', 'account', 'purchase', 'uom'],
    'data': [
        'security/psr_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        "report/report_action.xml",
        "report/report_templates.xml",
        'views/goods_receipt_views.xml',
        'views/trip_sheet_views.xml',
        'views/delivery_note_views.xml',
        'views/vehicle_gms_views.xml',
        'views/psr_menus.xml',
    ],
    'demo': [
        # 'data/demo_data.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
