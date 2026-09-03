import { expect } from "@playwright/test";

import BaseController from "./base";
import { fieldInput, fillField, fillLinkInput, newForm, slug, tableField } from "../frappe";

class Grid {
    constructor(page, fieldname) {
        this.page = page;
        this.fieldname = fieldname;
        this.root = page.locator(`.frappe-control[data-fieldname="${fieldname}"]`);
    }

    rows() {
        return this.root.locator(".grid-row[data-idx]");
    }

    row(idx) {
        return this.root.locator(`.grid-row[data-idx="${idx}"]`);
    }

    async assertRowCount(count) {
        await expect(this.rows()).toHaveCount(count);

        return this;
    }

    async ensureRows(count) {
        for (let existing = await this.rows().count(); existing < count; existing++) {
            await this.root.locator(".grid-add-row").click();
            await expect(this.rows()).toHaveCount(existing + 1);
        }

        return this.assertRowCount(count);
    }

    async openRow(idx) {
        const row = this.row(idx);

        if (!(await row.evaluate((el) => el.classList.contains("grid-row-open"))))
            await row.locator(".btn-open-row").click();

        await expect(row).toHaveClass(/grid-row-open/);

        return this;
    }

    async collapseRow(idx) {
        await this.row(idx).locator(".grid-collapse-row").click();
        await expect(this.row(idx)).not.toHaveClass(/grid-row-open/);

        return this;
    }

    /**
     * Set a Link field in a row through the grid's INLINE cell editor.
     *
     * Deliberately not via the expanded row form: that form re-renders while you
     * type and its first control (Barcode, on Sales Invoice items) steals focus,
     * so keystrokes end up in the wrong field. Clicking the collapsed cell swaps
     * its .static-area for a .form-control that owns the awesomplete outright.
     */
    async setLink(idx, fieldname, value) {
        await this.cell(idx, fieldname).click();

        const input = this.row(idx)
            .locator(`[data-fieldname="${fieldname}"] input.form-control:visible`)
            .first();

        await fillLinkInput(input, value);

        return this;
    }

    /**
     * Set a plain (non-Link) field in a row via the grid's inline cell editor.
     * Clicking the cell turns its .static-area into an editable .form-control, so
     * the row does not need expanding -- and expanding it would re-render the
     * control mid-edit.
     */
    async set(idx, fieldname, value) {
        const cell = this.cell(idx, fieldname);

        await cell.click();
        await cell.fill(String(value));
        await cell.blur();

        return this;
    }

    cell(idx, fieldname, fieldtype = "Data") {
        return tableField(this.page, this.fieldname, idx, fieldname, fieldtype);
    }
}

export default class FormController extends BaseController {
    constructor(page, doctype) {
        super(page);
        this.doctype = doctype;
    }

    async openNew() {
        await newForm(this.page, this.doctype);

        return this;
    }

    async open(name) {
        await this.page.goto(`/app/${slug(this.doctype)}/${encodeURIComponent(name)}`);
        await expect(this.page.locator("body")).toHaveAttribute("data-ajax-state", "complete");

        return this.waitForSettle();
    }

    async fill(fieldname, value, fieldtype = "Data") {
        await fillField(this.page, fieldname, value, fieldtype);

        return this;
    }

    async setLink(fieldname, value) {
        await fillField(this.page, fieldname, value, "Link");

        return this;
    }

    field(fieldname, fieldtype = "Data") {
        return fieldInput(this.page, fieldname, fieldtype);
    }

    grid(fieldname) {
        return new Grid(this.page, fieldname);
    }

    /** A JSON snapshot of cur_frm.doc, safe to assert on outside the page. */
    async doc() {
        return this.page.evaluate(() =>
            window.cur_frm ? JSON.parse(JSON.stringify(window.cur_frm.doc)) : null,
        );
    }

    /**
     * Poll cur_frm.doc until `pick` satisfies the matcher. Client scripts settle
     * the doc asynchronously (place_of_supply, taxes), so a single read races.
     *
     *   await form.docValue((doc) => doc.place_of_supply).toMatch(/^24-/);
     */
    docValue(pick, message) {
        return expect.poll(async () => pick((await this.doc()) || {}), { message });
    }

    async save() {
        const saved = this.page.waitForResponse(
            (response) =>
                response.url().includes("/api/method/frappe.desk.form.save.savedocs") &&
                response.request().method() === "POST",
        );

        await this.page.locator('.page-container:visible button[data-label="Save"]').first().click();

        const response = await saved;
        expect(response.status(), `savedocs: ${await response.text()}`).toBe(200);

        return this.waitForSettle();
    }

    async submit() {
        const saved = this.page.waitForResponse(
            (response) =>
                response.url().includes("/api/method/frappe.desk.form.save.savedocs") &&
                response.request().method() === "POST",
        );

        await this.page.locator('.page-container:visible button[data-label="Submit"]').first().click();

        await this.page.locator(".modal:visible .btn-modal-primary").first().click();

        const response = await saved;
        expect(response.status(), `savedocs (submit): ${await response.text()}`).toBe(200);

        await this.docValue((doc) => doc.docstatus, "docstatus should be 1 after submit").toBe(1);

        return this.waitForSettle();
    }

    /** Assert a scalar field on cur_frm.doc, polling while client scripts settle. */
    async assertValue(fieldname, expected) {
        await this.docValue((doc) => doc[fieldname], `${fieldname} should be ${expected}`).toBe(expected);

        return this;
    }

    /**
     * The msgprint/validation dialog frappe raises on a failed save. Use for the
     * cases where the *rejection* is the behaviour under test.
     */
    async assertErrorDialog(pattern) {
        await expect(this.page.locator(".modal:visible .modal-body").first()).toContainText(pattern);

        return this;
    }

    async dismissDialog() {
        const modal = this.page.locator(".modal:visible").first();

        if (await modal.count()) {
            await modal.locator(".modal-header .btn-modal-close, .btn-modal-primary").first().click();
            await expect(modal).toBeHidden();
        }

        return this;
    }

    async assertStatus(status) {
        await expect(
            this.page.locator('.page-container:visible [data-testid="page-status"]').first(),
        ).toContainText(status);

        return this;
    }
}
