from app.models.channel_connection import ChannelConnection
from app.services.channels.base import ChannelAdapter


def get_channel_adapter(connection: ChannelConnection) -> ChannelAdapter:
    """Dispatch to the concrete adapter for a connection's channel_type.

    Imports are deferred to the branch that needs them so this factory can be
    imported by pipeline nodes without creating an import cycle with the
    concrete adapter modules.
    """
    if connection.channel_type == "telegram":
        from app.services.channels.telegram import TelegramAdapter

        return TelegramAdapter(
            bot_token=connection.credentials["bot_token"],
            channel_connection_id=connection.id,
        )
    if connection.channel_type == "whatsapp":
        from app.services.channels.whatsapp import WhatsAppAdapter

        return WhatsAppAdapter(
            phone_number_id=connection.credentials["phone_number_id"],
            access_token=connection.credentials["access_token"],
            channel_connection_id=connection.id,
        )
    if connection.channel_type == "email":
        from app.services.channels.email_inbound import EmailInboundAdapter

        return EmailInboundAdapter(
            inbound_slug=connection.credentials["inbound_slug"],
            channel_connection_id=connection.id,
        )
    raise ValueError(f"Unknown channel_type: {connection.channel_type!r}")
