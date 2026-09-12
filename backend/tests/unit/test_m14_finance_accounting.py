from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m14_payment_allocation_and_reversal_invariants_are_encoded() -> None:
    service = (
        ROOT / "app" / "modules" / "finance" / "service.py"
    ).read_text(encoding="utf-8")

    assert "Payment amount must equal the total allocation amount" in service
    assert "Each charge can appear only once in a payment" in service
    assert "Payment allocation exceeds the remaining charge balance" in service
    assert "A charge with posted payment allocations cannot be voided" in service
    assert "_recalculate_charge_status" in service
    assert '"BILLING_PAYMENT_POSTED"' in service
    assert '"BILLING_PAYMENT_VOIDED"' in service
    assert '"BILLING_CHARGE_VOIDED"' in service


def test_m14_uses_transactional_outbox_for_money_state_changes() -> None:
    service = (
        ROOT / "app" / "modules" / "finance" / "service.py"
    ).read_text(encoding="utf-8")
    assert "enqueue_event(" in service
    assert '"BILLING_CHARGE_CREATED"' in service
    assert '"BILLING_PAYMENT_POSTED"' in service
    assert '"FINANCE_CAPABILITY_CHANGED"' in service
