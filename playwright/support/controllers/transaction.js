import { expect } from "@playwright/test";

import FormController from "./form";
import { placeOfSupplyPattern } from "../test_records";

export default class TransactionController extends FormController {
    async setCustomer(customer) {
        await this.setLink("customer", customer);

        return this.waitForSettle();
    }

    async setAddress(fieldname, address) {
        await this.setLink(fieldname, address);

        return this.waitForSettle();
    }

    async setSupplier(supplier) {
        await this.setLink("supplier", supplier);

        return this.waitForSettle();
    }

    async setBillNo(value) {
        return this.fill("bill_no", value || `UI-${Date.now().toString().slice(-10)}`, "Data");
    }

    async addItem(itemCode, { qty = 1, rate = 100 } = {}) {
        const items = this.grid("items");

        await items.ensureRows(1);
        await items.setLink(1, "item_code", itemCode);
        await this.waitForSettle();

        await items.set(1, "qty", qty);
        await items.set(1, "rate", rate);

        return this.waitForSettle();
    }

    async assertPlaceOfSupplyMatches(gstin) {
        await this.docValue(
            (doc) => doc.place_of_supply,
            `place_of_supply should be in the company's state (${gstin})`,
        ).toMatch(placeOfSupplyPattern(gstin));

        return this;
    }

    async assertIntraStateTaxHeads() {
        // Poll first: taxes are populated by the tax-template client script.
        await this.docValue(
            (doc) => (doc.taxes || []).map((row) => row.account_head),
            "expected exactly two GST tax rows (CGST + SGST)",
        ).toHaveLength(2);

        const doc = await this.doc();
        const heads = doc.taxes.map((row) => row.account_head);

        expect(doc.taxes_and_charges, "a GST tax template was applied").toBeTruthy();
        expect(
            heads.some((head) => /CGST/.test(head)),
            `CGST row in ${heads}`,
        ).toBe(true);
        expect(
            heads.some((head) => /SGST/.test(head)),
            `SGST row in ${heads}`,
        ).toBe(true);
        expect(
            heads.some((head) => /IGST/.test(head)),
            `no IGST row in ${heads}`,
        ).toBe(false);

        const [cgst, sgst] = doc.taxes;
        expect(cgst.rate, "CGST rate is set").toBeGreaterThan(0);
        expect(sgst.rate, "SGST rate equals CGST rate").toBe(cgst.rate);

        return this;
    }

    /** The tax rows currently on the doc, as account_head strings. */
    async taxHeads() {
        const doc = await this.doc();

        return (doc?.taxes || []).map((row) => row.account_head);
    }

    async assertInterStateTaxHeads() {
        await this.docValue(
            (doc) => (doc.taxes || []).map((row) => row.account_head),
            "expected exactly one GST tax row (IGST)",
        ).toHaveLength(1);

        const doc = await this.doc();
        const heads = doc.taxes.map((row) => row.account_head);

        expect(doc.taxes_and_charges, "a GST tax template was applied").toBeTruthy();
        expect(
            heads.some((head) => /IGST/.test(head)),
            `IGST row in ${heads}`,
        ).toBe(true);
        expect(
            heads.some((head) => /CGST|SGST/.test(head)),
            `no CGST/SGST row in ${heads}`,
        ).toBe(false);
        expect(doc.taxes[0].rate, "IGST rate is set").toBeGreaterThan(0);

        return this;
    }

    async assertNoTaxRows() {
        await this.docValue(
            (doc) => (doc.taxes || []).filter((row) => /CGST|SGST|IGST/.test(row.account_head)),
            "expected no GST tax rows",
        ).toHaveLength(0);

        return this;
    }

    async assertItemsField(fieldname, expected) {
        await this.docValue(
            (doc) => (doc.items || []).map((row) => row[fieldname]),
            `every item row should have ${fieldname} = ${expected}`,
        ).toEqual(expect.arrayContaining([expected]));

        const doc = await this.doc();
        for (const [idx, row] of (doc.items || []).entries())
            expect(row[fieldname], `items[${idx}].${fieldname}`).toBe(expected);

        return this;
    }
}
