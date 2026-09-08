class TestCiFailureCheck:
    def test_locator_that_does_not_exist(self):
        form = self.form_page("Purchase Invoice")
        form.fill_fields({"this_field_does_not_exist": "x"})

    def test_assertion_that_cannot_hold(self):
        form = self.form_page("Purchase Invoice")

        assert form.get_status() == "Submitted", "a brand new form is never Submitted"
