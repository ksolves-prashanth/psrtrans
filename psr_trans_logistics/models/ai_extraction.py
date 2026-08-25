# -*- coding: utf-8 -*-
import base64
import json
import logging

import requests

from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_API_VERSION = '2023-06-01'
# Vision-capable model used for document extraction. Confirm the current
# recommended model string in Anthropic's docs before going live:
# https://docs.claude.com
ANTHROPIC_MODEL = 'claude-sonnet-5'

EXTRACTION_PROMPT = """You are extracting structured data from a scanned e-way bill \
or invoice for a transport/logistics Goods Receipt (GR). Read the attached document \
and return ONLY a JSON object (no markdown, no commentary) with these keys, using \
null where a value is not present in the document:
{
  "eway_bill_number": string or null,
  "eway_bill_date": "YYYY-MM-DD" or null,
  "invoice_number": string or null,
  "invoice_value": number or null,
  "package_count": integer or null,
  "goods_value": number or null,
  "product_type": string or null,
  "consignor_name": string or null,
  "consignee_name": string or null
}"""


class PsrAiExtractionMixin(models.AbstractModel):
    """Reusable mixin: any model with a `source_document` Binary field can offer
    one-click AI auto-fill from an uploaded e-way bill / invoice scan, instead of
    re-typing details from a paper document. Kept as a mixin so the same button
    can later be added to Delivery Note or other document models with minimal code."""
    _name = 'psr.ai.extraction.mixin'
    _description = 'AI Document Extraction Mixin'

    def _get_anthropic_api_key(self):
        api_key = self.env['ir.config_parameter'].sudo().get_param('psr_trans_logistics.anthropic_api_key')
        if not api_key:
            raise UserError(_(
                'No Anthropic API key configured. Ask an administrator to set '
                '"psr_trans_logistics.anthropic_api_key" under Settings > Technical > '
                'Parameters > System Parameters.'
            ))
        return api_key

    def action_ai_extract_details(self):
        """Button action: sends the attached scan to Claude and auto-fills the
        record's fields from the structured JSON response."""
        self.ensure_one()
        if not self.source_document:
            raise UserError(_('Attach an e-way bill / invoice scan first (image or PDF).'))

        extracted = self._call_claude_extract(self.source_document, self.source_document_filename or '')
        vals = self._map_extraction_to_vals(extracted)
        if vals:
            self.write(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AI Extraction Complete'),
                'message': _('Fields updated from the attached document. Please verify before booking.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def _call_claude_extract(self, document_base64, filename):
        media_type = 'application/pdf' if filename.lower().endswith('.pdf') else 'image/jpeg'
        block_type = 'document' if media_type == 'application/pdf' else 'image'

        payload = {
            'model': ANTHROPIC_MODEL,
            'max_tokens': 1024,
            'messages': [{
                'role': 'user',
                'content': [
                    {
                        'type': block_type,
                        'source': {
                            'type': 'base64',
                            'media_type': media_type,
                            'data': document_base64.decode() if isinstance(document_base64, bytes)
                            else document_base64,
                        },
                    },
                    {'type': 'text', 'text': EXTRACTION_PROMPT},
                ],
            }],
        }
        headers = {
            'x-api-key': self._get_anthropic_api_key(),
            'anthropic-version': ANTHROPIC_API_VERSION,
            'content-type': 'application/json',
        }
        try:
            response = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            _logger.exception('Anthropic API call failed for AI extraction')
            raise UserError(_('AI extraction failed: %s') % str(exc)) from exc

        data = response.json()
        text_blocks = [block.get('text', '') for block in data.get('content', []) if block.get('type') == 'text']
        raw_text = ''.join(text_blocks).strip()
        try:
            return json.loads(raw_text)
        except (ValueError, TypeError) as exc:
            _logger.error('Could not parse AI extraction response: %s', raw_text)
            raise UserError(_('AI response could not be parsed. Please fill in the fields manually.')) from exc

    def _map_extraction_to_vals(self, extracted):
        """Override per model - base mixin only knows the common GR-style fields."""
        field_map = {
            'eway_bill_number': 'eway_bill_number',
            'eway_bill_date': 'eway_bill_date',
            'invoice_number': 'invoice_number',
            'invoice_value': 'invoice_value',
            'package_count': 'package_count',
            'goods_value': 'goods_value',
            'product_type': 'product_type',
        }
        vals = {}
        for json_key, field_name in field_map.items():
            if json_key in extracted and extracted[json_key] not in (None, '') and field_name in self._fields:
                vals[field_name] = extracted[json_key]
        return vals
