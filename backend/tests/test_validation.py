import pandas as pd
import pytest

from app.constants import Book
from app.errors import FileValidationError
from app.services.validation import validate_frame
from tests.conftest import asset_row, history_rows, liability_row


def rules(outcome):
    return {(e["column_name"], e["rule"]) for e in outcome.errors}


def test_valid_asset_rows_are_accepted():
    outcome = validate_frame(pd.DataFrame([asset_row(1), asset_row(2)]), Book.ASSET)
    assert len(outcome.records) == 2 and not outcome.errors
    assert str(outcome.records[0]["loan_amount"]) == "1000000"


def test_excel_midnight_timestamp_is_accepted():
    outcome = validate_frame(pd.DataFrame([asset_row(1, Transaction_Date="2026-09-30 00:00:00")]), Book.ASSET)
    assert len(outcome.records) == 1


@pytest.mark.parametrize("override,column", [
    ({"Transaction_ID": "LN-1"}, "Transaction_ID"),
    ({"Entity": "IBC India"}, "Entity"),
    ({"Customer_ID": "C-1"}, "Customer_ID"),
    ({"Loan_Amount": "-5"}, "Loan_Amount"),
    ({"Loan_Amount": "abc"}, "Loan_Amount"),
    ({"Currency": "INR"}, "Currency"),
    ({"Transaction_Date": "32/13/2026"}, "Transaction_Date"),
    ({"Interest_Rate_Pct": "101"}, "Interest_Rate_Pct"),
    ({"Loan_Type": "Loan-Type-Z"}, "Loan_Type"),
    ({"Customer_Segment": "VIP"}, "Customer_Segment"),
    ({"Client_Rating": "6"}, "Client_Rating"),
    ({"Client_Rating": "2.5"}, "Client_Rating"),
    ({"Market_Interest_Rate_Pct": ""}, "Market_Interest_Rate_Pct"),
])
def test_invalid_asset_values_are_rejected(override, column):
    outcome = validate_frame(pd.DataFrame([asset_row(1, **override)]), Book.ASSET)
    assert not outcome.records
    assert column in {c for c, _ in rules(outcome)}


def test_entity_location_mismatch_rejected():
    outcome = validate_frame(pd.DataFrame([asset_row(1, Entity="IBC UK", Location="Paris")]), Book.ASSET)
    assert ("Location", "entity_location") in rules(outcome)


def test_maturity_before_transaction_rejected():
    outcome = validate_frame(pd.DataFrame([liability_row(1, Transaction_Date="2026-10-10", Maturity_Date="2026-10-01")]), Book.LIABILITY)
    assert ("Maturity_Date", "maturity_before_start") in rules(outcome)


def test_duplicate_row_and_duplicate_id_rejected():
    rows = [asset_row(1), asset_row(1), asset_row(1, Loan_Amount="5")]
    outcome = validate_frame(pd.DataFrame(rows), Book.ASSET)
    assert len(outcome.records) == 1
    assert {"duplicate_row", "duplicate_id"} <= {r for _, r in rules(outcome)}


def test_missing_column_fails_whole_file():
    with pytest.raises(FileValidationError):
        validate_frame(pd.DataFrame([asset_row(1)]).drop(columns=["Currency"]), Book.ASSET)


def test_historical_type_case_insensitive_and_blank_closure_allowed():
    row = history_rows(1)[0] | {"Type": "liability", "Actual_Closure_Date": ""}
    outcome = validate_frame(pd.DataFrame([row]), Book.HISTORICAL)
    assert outcome.records[0]["type"] == "Liability"
    assert outcome.records[0]["actual_closure_date"] is None


def test_historical_unknown_type_rejected():
    outcome = validate_frame(pd.DataFrame([history_rows(1)[0] | {"Type": "Deposit"}]), Book.HISTORICAL)
    assert ("Type", "invalid_value") in rules(outcome)
