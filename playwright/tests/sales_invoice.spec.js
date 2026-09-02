import { expect, test } from "../support/fixtures";
import TransactionController from "../support/controllers/transaction";
import { getRecord, placeOfSupplyPattern } from "../support/test_records";

const company = getRecord("Company", "_Test Indian Registered Company");
const customer = getRecord("Customer", "_Test Registered Customer");
const item = getRecord("Item", "_Test Trading Goods 1");

// _Test Registered Customer has addresses in both Gujarat (24, the company's own
// state) and Karnataka (29). Addresses are auto-named, so they are resolved by
// GSTIN at runtime rather than hardcoded.
const OUT_OF_STATE_GSTIN = "29AAACI1195H2ZH";

async function addressByGstin(api, gstin) {
    const [address] = await api.getList("Address", {
        fields: ["name", "gstin"],
        filters: { gstin },
        limit: 1,
    });

    expect(address, `no Address seeded with gstin ${gstin}`).toBeTruthy();

    return address.name;
}

/** A saved draft Sales Invoice for the in-state customer. */
async function draftInvoice(desk) {
    const form = new TransactionController(desk, "Sales Invoice");

    await form.openNew();
    await form.setCustomer(customer.name);
    await form.addItem(item.name);
    await form.save();

    return form;
}

test.describe("Sales Invoice", () => {
    test("applies intra-state GST for a customer in the company's state", async ({ desk }) => {
        const form = await draftInvoice(desk);

        await form.assertValue("gst_category", customer.gst_category);
        await form.assertPlaceOfSupplyMatches(company.gstin);
        await form.assertIntraStateTaxHeads();

        // Per-item GST details are derived server-side on save.
        await form.assertItemsField("gst_treatment", "Taxable");

        const doc = await form.doc();
        for (const [idx, row] of doc.items.entries()) {
            expect(row.taxable_value, `items[${idx}].taxable_value`).toBeGreaterThan(0);
            expect(row.gst_hsn_code, `items[${idx}].gst_hsn_code`).toBeTruthy();
        }

        await form.assertStatus("Draft");
    });

    test("switches to IGST when the billing address moves out of state", async ({ desk, api }) => {
        const form = await draftInvoice(desk);
        await form.assertIntraStateTaxHeads();

        const outOfState = await addressByGstin(api, OUT_OF_STATE_GSTIN);

        await form.setAddress("customer_address", outOfState);
        await form.save();

        await form
            .docValue(
                (doc) => doc.place_of_supply,
                "place_of_supply should follow the new address, not the company",
            )
            .not.toMatch(placeOfSupplyPattern(company.gstin));

        await form.assertInterStateTaxHeads();
    });

    test("sets an e-Waybill status on submit", async ({ desk }) => {
        const form = await draftInvoice(desk);

        await form.submit();
        await form.assertStatus("Unpaid");

        // The exact value depends on GST Settings (e-waybill enabled, thresholds),
        // so this asserts only that the field is resolved rather than left blank.
        await form
            .docValue(
                (doc) => doc.e_waybill_status,
                "e_waybill_status should be set once the invoice is submitted",
            )
            .toBeTruthy();
    });
});
