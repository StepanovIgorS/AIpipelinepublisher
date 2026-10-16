import pytest

from unittest.mock import patch, ANY, AsyncMock
from types import SimpleNamespace

from api.main import subscription_chosen, pre_checkout, successful_payment
from api.model import Payments
from aiogram.types import Message



@pytest.mark.anyio
async def test_subscription_chosen_success():
    with (
        patch("api.main.db.execute") as mock_execute,
        patch("api.main.bot.send_invoice") as mock_invoice
    ):
        mock_callback = AsyncMock()
        mock_state = AsyncMock()
        mock_callback.message = AsyncMock(spec=Message)
        mock_callback.data = "3_months"
        mock_callback.from_user.id = 123
        mock_callback.message.delete = AsyncMock()
        mock_callback.answer = AsyncMock()
        mock_state.set_state = AsyncMock()
        mock_state.clear = AsyncMock()
        mock_invoice.return_value = SimpleNamespace(message_id=999)

        await subscription_chosen(mock_callback, mock_state)

        mock_callback.message.delete.assert_awaited_once()
        mock_invoice.assert_awaited_once_with(chat_id=123, title=ANY, description=ANY, payload=ANY, currency="RUB", provider_token=ANY, prices=ANY)
        invoice_args, invoice_kwargs = mock_invoice.call_args
        db_args, db_kwargs = mock_execute.call_args
        assert invoice_kwargs["payload"] == str(db_args[1])
        mock_execute.assert_awaited_once_with(ANY, ANY, 123, 3, 999)
        mock_callback.answer.assert_awaited_once()
        mock_state.set_state.assert_awaited_once_with(Payments.pending)


@pytest.mark.anyio
async def test_subscription_chosen_wrong_data():
    with (
        patch("api.main.db.execute") as mock_execute,
        patch("api.main.bot.send_invoice") as mock_invoice
    ):
        mock_callback = AsyncMock()
        mock_state = AsyncMock()
        mock_callback.message = AsyncMock(spec=Message)
        mock_callback.data = "4_months"
        mock_callback.from_user.id = 123
        mock_callback.message.delete = AsyncMock()
        mock_callback.answer = AsyncMock()
        mock_state.set_state = AsyncMock()
        mock_state.clear = AsyncMock()
        mock_invoice.return_value = SimpleNamespace(message_id=999)

        await subscription_chosen(mock_callback, mock_state)

        mock_callback.message.delete.assert_awaited_once()
        mock_invoice.assert_not_awaited()
        mock_execute.assert_not_awaited()
        mock_callback.answer.assert_awaited_once_with(ANY,show_alert=True)
        mock_state.set_state.assert_not_awaited()
        mock_state.clear.assert_awaited_once()


@pytest.mark.anyio
async def test_pre_checkout_success():
    with patch("api.main.db.fetchone") as mock_fetchone:
        query = AsyncMock()
        query.invoice_payload = "test-uuid"
        query.from_user.id = 123
        query.answer = AsyncMock()
        mock_fetchone.return_value = {"user_id": 123, "status": "pending"}

        await pre_checkout(query)

        query.answer.assert_awaited_once_with(ok=True)
        mock_fetchone.assert_awaited_once_with(ANY, "test-uuid")


@pytest.mark.anyio
async def test_pre_checkout_bill_status_not_pending():
    with patch("api.main.db.fetchone") as mock_fetchone:
        query = AsyncMock()
        query.invoice_payload = "test-uuid"
        query.from_user.id = 123
        query.answer = AsyncMock()
        mock_fetchone.return_value = {"user_id": 123, "status": "paid"}

        await pre_checkout(query)

        query.answer.assert_awaited_once_with(ok=False, error_message=ANY)
        mock_fetchone.assert_awaited_once_with(ANY, "test-uuid")


@pytest.mark.anyio
async def test_pre_checkout_bill_belongs_to_other_user():
    with patch("api.main.db.fetchone") as mock_fetchone:
        query = AsyncMock()
        query.invoice_payload = "test-uuid"
        query.from_user.id = 123
        query.answer = AsyncMock()
        mock_fetchone.return_value = {"user_id": 432, "status": "pending"}

        await pre_checkout(query)

        query.answer.assert_awaited_once_with(ok=False, error_message=ANY)
        mock_fetchone.assert_awaited_once_with(ANY, "test-uuid")


@pytest.mark.anyio
async def test_successful_payment_success():
    with (
        patch("api.main.db.fetchone") as mock_fetchone,
        patch("api.main.db.execute") as mock_execute,
        patch("api.main.bot.delete_message") as mock_delete
    ):
        mock_fetchone.return_value = {"status": "pending", "plan": 3, "invoice_message_id": 1234}
        message = AsyncMock()
        message.answer = AsyncMock()
        state = AsyncMock()
        state.clear = AsyncMock()
        message.from_user.id = 123
        message.successful_payment.invoice_payload = "test-uuid"

        await successful_payment(message, state)

        mock_fetchone.assert_awaited_once_with(ANY, "test-uuid")
        mock_execute.assert_awaited_once_with(ANY, "test-uuid", 3, 123)
        mock_delete.assert_awaited_once_with(chat_id=123, message_id=1234)
        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()


@pytest.mark.anyio
async def test_successful_payment_bill_already_paid():
    with (
        patch("api.main.db.fetchone") as mock_fetchone,
        patch("api.main.db.execute") as mock_execute,
        patch("api.main.bot.delete_message") as mock_delete
    ):
        mock_fetchone.return_value = {"status": "paid", "plan": 3, "invoice_message_id": 1234}
        message = AsyncMock()
        message.answer = AsyncMock()
        state = AsyncMock()
        state.clear = AsyncMock()
        message.from_user.id = 123
        message.successful_payment.invoice_payload = "test-uuid"

        await successful_payment(message, state)

        mock_fetchone.assert_awaited_once_with(ANY, "test-uuid")
        mock_execute.assert_not_awaited()
        mock_delete.assert_not_awaited()
        state.clear.assert_not_awaited()
        message.answer.assert_not_awaited()