# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.core.doctype.user_permission.user_permission import get_permitted_documents
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.utils.isd import (
    get_purchase_invoices_distribution_summary,
    get_report_company_currency,
    validate_common_report_filters,
)

# Purchase Invoice header columns pulled via get_purchase_invoices_distribution_summary
PARENT_EXTRA_FIELDS = ["company_gstin", "supplier_gstin", "place_of_supply", "base_grand_total"]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if filters.get("date_range"):
        filters.from_date, filters.to_date = filters.date_range
    validate_common_report_filters(filters)
    return get_columns(filters), get_data(filters)


def _get_candidate_purchase_invoices(filters):
    """Return ordered {purchase_invoice: taxable_value} for PIs matching the report filters."""
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    query = (
        frappe.qb.from_(pi)
        .join(pi_item)
        .on(pi_item.parent == pi.name)
        .select(pi.name.as_("purchase_invoice"), Sum(pi_item.net_amount).as_("taxable_value"))
        .where(pi.docstatus == 1)
        .where(pi.is_isd_applicable == 1)
        .where(pi.posting_date[filters.from_date : filters.to_date])
        .groupby(pi.name)
        .orderby(pi.posting_date)
    )

    if filters.get("company"):
        query = query.where(pi.company == filters.company)
    else:
        permitted = get_permitted_documents("Company")
        if permitted:
            query = query.where(pi.company.isin(permitted))

    if filters.get("company_gstin"):
        query = query.where(pi.company_gstin == filters.company_gstin)

    return {row.purchase_invoice: flt(row.taxable_value) for row in query.run(as_dict=True)}


def _get_parent_rows(purchase_invoices):
    """Collapse the per-(pi, is_ineligible) summary into one parent dict per purchase invoice."""
    parents = {}
    for row in get_purchase_invoices_distribution_summary(
        purchase_invoices, extra_fields=PARENT_EXTRA_FIELDS
    ):
        parent = parents.setdefault(
            row.purchase_invoice,
            frappe._dict(
                company_gstin=row.company_gstin,
                supplier_gstin=row.supplier_gstin,
                posting_date=row.posting_date,
                place_of_supply=row.place_of_supply,
                total_value=flt(row.base_grand_total),
                total_eligible=0.0,
                total_ineligible=0.0,
                remaining_eligible=0.0,
                remaining_ineligible=0.0,
            ),
        )

        if cint(row.is_ineligible_for_itc):
            parent.total_ineligible += flt(row.total_tax)
            parent.remaining_ineligible += flt(row.available_tax)
        else:
            parent.total_eligible += flt(row.total_tax)
            parent.remaining_eligible += flt(row.available_tax)

    return parents


def _get_child_rows(purchase_invoices):
    """Return {purchase_invoice: [source item rows]} from submitted ISD invoices."""
    children = {}
    if not purchase_invoices:
        return children

    isi = frappe.qb.DocType("ISD Invoice Source Item")
    rows = (
        frappe.qb.from_(isi)
        .where(isi.docstatus == 1)
        .where(isi.purchase_invoice.isin(list(purchase_invoices)))
        .select(
            isi.parent.as_("isd_invoice"),
            isi.purchase_invoice,
            isi.is_ineligible_for_itc,
            *[Sum(getattr(isi, f"distributed_{t}")).as_(f"distributed_{t}") for t in GST_TAX_TYPES],
        )
        .groupby(isi.parent, isi.purchase_invoice, isi.is_ineligible_for_itc)
        .orderby(isi.parent)
        .run(as_dict=True)
    )

    for row in rows:
        children.setdefault(row.purchase_invoice, []).append(row)

    return children


def get_data(filters):
    candidates = _get_candidate_purchase_invoices(filters)
    pi_names = list(candidates)

    parents = _get_parent_rows(pi_names)
    children = _get_child_rows(pi_names)

    result = []
    for pi_name in pi_names:
        parent = parents.get(pi_name)
        if not parent:
            continue

        # pending_distribution: keep only PIs with nothing distributed yet
        if filters.get("pending_distribution"):
            if not (
                parent.remaining_eligible == parent.total_eligible
                and parent.remaining_ineligible == parent.total_ineligible
            ):
                continue

        child_rows = children.get(pi_name, [])
        distributed_totals = {
            f"distributed_{t}": sum(flt(child.get(f"distributed_{t}")) for child in child_rows)
            for t in GST_TAX_TYPES
        }

        result.append(
            {
                "purchase_invoice": pi_name,
                "company_gstin": parent.company_gstin,
                "supplier_gstin": parent.supplier_gstin,
                "posting_date": parent.posting_date,
                "place_of_supply": parent.place_of_supply,
                "total_value": parent.total_value,
                "taxable_value": candidates.get(pi_name),
                "total_eligible": parent.total_eligible,
                "total_ineligible": parent.total_ineligible,
                "remaining_eligible": parent.remaining_eligible,
                "remaining_ineligible": parent.remaining_ineligible,
                **distributed_totals,
                "indent": 0,
                "is_group": 1,
            }
        )

        for child in child_rows:
            result.append(
                {
                    "purchase_invoice": pi_name,
                    "isd_invoice": child.isd_invoice,
                    "is_ineligible_for_itc": cint(child.is_ineligible_for_itc),
                    "distributed_cgst": flt(child.distributed_cgst),
                    "distributed_sgst": flt(child.distributed_sgst),
                    "distributed_igst": flt(child.distributed_igst),
                    "distributed_cess": flt(child.distributed_cess),
                    "distributed_cess_non_advol": flt(child.distributed_cess_non_advol),
                    "indent": 1,
                    "is_group": 0,
                }
            )

    return result


def get_columns(filters):
    company_currency = get_report_company_currency(filters)

    return [
        {
            "fieldname": "purchase_invoice",
            "label": _("Invoice No"),
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "width": 220,
            "sticky": True,
        },
        {
            "fieldname": "isd_invoice",
            "label": _("ISD Invoice"),
            "fieldtype": "Link",
            "options": "ISD Invoice",
            "width": 180,
        },
        {
            "fieldname": "company_gstin",
            "label": _("Company GSTIN"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "supplier_gstin",
            "label": _("Supplier GSTIN"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "posting_date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "place_of_supply",
            "label": _("POS"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "is_ineligible_for_itc",
            "label": _("Ineligible for ITC"),
            "fieldtype": "Check",
            "width": 110,
        },
        {
            "fieldname": "total_value",
            "label": _("Total Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 120,
        },
        {
            "fieldname": "taxable_value",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 120,
        },
        {
            "fieldname": "total_eligible",
            "label": _("Total Eligible"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "total_ineligible",
            "label": _("Total Ineligible"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "remaining_eligible",
            "label": _("Remaining Eligible"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 150,
        },
        {
            "fieldname": "remaining_ineligible",
            "label": _("Remaining Ineligible"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 150,
        },
        {
            "fieldname": "distributed_cgst",
            "label": _("Distributed CGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "distributed_sgst",
            "label": _("Distributed SGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "distributed_igst",
            "label": _("Distributed IGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "distributed_cess",
            "label": _("Distributed Cess"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "distributed_cess_non_advol",
            "label": _("Distributed Cess (Non-Advol)"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 160,
        },
    ]
