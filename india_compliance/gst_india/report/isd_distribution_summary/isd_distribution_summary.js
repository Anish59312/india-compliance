// Copyright (c) 2026, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["ISD Distribution Summary"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            on_change: function () {
                const company = frappe.query_report.get_filter_value("company");
                if (!company) {
                    frappe.query_report.set_filter_value({ company_gstin: "" });
                    return;
                }
                frappe.call({
                    method: "india_compliance.gst_india.utils.isd.get_company_isd_gstin",
                    args: { company },
                    callback: function (r) {
                        frappe.query_report.set_filter_value({ company_gstin: r.message || "" });
                    },
                });
            },
            get_query: function () {
                return { filters: { country: "India" } };
            },
        },
        {
            fieldname: "date_range",
            label: __("Date Range"),
            fieldtype: "DateRange",
            default: [india_compliance.last_month_start(), india_compliance.last_month_end()],
            reqd: 1,
            width: "80",
        },
        {
            fieldname: "company_gstin",
            label: __("Company GSTIN"),
            fieldtype: "Autocomplete",
            depends_on: "company",
            get_query() {
                const company = frappe.query_report.get_filter_value("company");
                return india_compliance.get_gstin_query(company);
            },
        },
        {
            fieldname: "pending_distribution",
            label: __("Pending Distribution"),
            fieldtype: "Check",
            default: 0,
        },
    ],
    tree: true,
    parent_field: "purchase_invoice",
    name_field: "purchase_invoice",
    initial_depth: 0,
    after_datatable_render: function (datatable) {
        // Parent (Purchase Invoice) and child (ISD Invoice) rows carry different
        // meaningful columns. Show parent columns while collapsed, swap to child
        // columns once any node is expanded. `purchase_invoice` always stays.
        const CHILD_FIELDS = [
            "isd_invoice",
            "is_ineligible_for_itc",
            "distributed_cgst",
            "distributed_sgst",
            "distributed_igst",
            "distributed_cess",
            "distributed_cess_non_advol",
        ];
        const ALWAYS_FIELDS = ["purchase_invoice"];

        const child_idx = [];
        const parent_idx = [];
        for (const col of datatable.getColumns()) {
            if (typeof col.colIndex !== "number" || !col.id) continue;
            if (ALWAYS_FIELDS.includes(col.id)) continue;
            (CHILD_FIELDS.includes(col.id) ? child_idx : parent_idx).push(col.colIndex);
        }

        const rule = (cls, idx) =>
            idx.map((i) => `.${cls} .dt-cell--col-${i} { display: none !important; }`).join("\n");

        const style_id = "ic-isd-column-toggle-style";
        let style_el = document.getElementById(style_id);
        if (!style_el) {
            style_el = document.createElement("style");
            style_el.id = style_id;
            document.head.appendChild(style_el);
        }
        style_el.textContent = [rule("ic-collapsed", child_idx), rule("ic-expanded", parent_idx)].join("\n");

        const wrapper = datatable.wrapper;

        const sync = () => {
            const any_open = [...wrapper.querySelectorAll(".dt-tree-node__toggle")].some(
                (toggle) => !toggle.closest(".dt-cell").classList.contains("dt-cell--tree-close"),
            );
            wrapper.classList.toggle("ic-expanded", any_open);
            wrapper.classList.toggle("ic-collapsed", !any_open);
        };

        wrapper.addEventListener("click", (e) => {
            if (e.target.closest(".dt-tree-node__toggle")) setTimeout(sync, 0);
        });

        sync();
    },
};
