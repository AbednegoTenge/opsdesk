"""Delivery channels. Each `send` either succeeds, raises PermanentDeliveryError (do not
retry), or raises anything else (treated as transient and retried by the task)."""

import smtplib

from django.conf import settings
from django.core.mail import send_mail

from .models import Channel, Notification, NotificationDelivery


class PermanentDeliveryError(Exception):
    pass


def send_in_app(delivery: NotificationDelivery) -> Notification:
    return Notification.objects.create(
        recipient=delivery.recipient,
        incident=delivery.incident,
        kind=delivery.kind,
        title=delivery.subject.removeprefix("[OpsDesk] "),
        body=delivery.body,
    )


def send_email(delivery: NotificationDelivery) -> None:
    if not delivery.recipient.email:
        raise PermanentDeliveryError("recipient has no email address")
    try:
        send_mail(
            delivery.subject,
            delivery.body,
            settings.DEFAULT_FROM_EMAIL,
            [delivery.recipient.email],
            fail_silently=False,
        )
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
        raise PermanentDeliveryError(str(exc)) from exc


SENDERS = {Channel.IN_APP: send_in_app, Channel.EMAIL: send_email}
