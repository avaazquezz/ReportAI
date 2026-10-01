"""Everything the bot says to a person, in the tenant's language (IA-5).

One catalog instead of strings scattered through the nodes: a missing key or a placeholder
mismatch between languages is caught by tests/test_i18n.py, not by a sales rep reading
half-English replies."""

from datetime import date, time
from typing import Final

DEFAULT_LANGUAGE: Final = "es"
SUPPORTED_LANGUAGES: Final = ("es", "en")

LANGUAGE_NAMES: Final = {"es": "Spanish", "en": "English"}

_MESSAGES: Final[dict[str, dict[str, str]]] = {
    "es": {
        # channel guards
        "rejected_sender": "Lo siento, no tienes acceso a este canal. Pide a tu administrador un enlace de invitación, o pásale este identificador: {sender}",
        "enrolled": "¡Hola, {name}! Ya puedes enviarme tus informes: una nota de voz o un texto con los datos, y fotos si hacen falta.",
        "welcome": "Envíame una nota de voz o un texto con los datos del informe (y fotos si hacen falta) y preparo el documento.",
        "rate_limited": "Has alcanzado el límite de informes por hora. Inténtalo de nuevo más tarde.",
        "spend_capped": "El servicio ha alcanzado su límite de uso diario. Inténtalo de nuevo mañana.",
        "busy": "Sigo procesando tu informe anterior. En cuanto termine te escribo.",
        "empty_message": "No he entendido ese mensaje. Envíame una nota de voz o un texto con los datos del informe.",
        "unsupported_message": "Ese tipo de mensaje no lo puedo usar todavía. Envíame una nota de voz, un texto o una foto.",
        "not_configured": "Este servicio aún no está configurado. Avisa a tu administrador, por favor.",
        "voice_not_configured": "Las notas de voz aún no están activadas. Envíame el informe por escrito, por favor.",
        # photos
        "photo_attached": "📎 Foto añadida al informe.",
        "photo_without_report": "He guardado la foto. Envíame la nota de voz o el texto del informe y la adjunto.",
        "photo_failed": "No he podido descargar la foto. Envíala de nuevo, por favor.",
        # document type
        "doctype_prompt": "¿Qué tipo de documento quieres generar?",
        "doctype_unclear": "No he reconocido ese tipo. Elige uno de la lista.",
        # approval
        "approval_header": "Esto es lo que he extraído para tu {doc_type}:",
        "approval_footer": "Confirma para generar el documento, o dime qué hay que corregir (texto o nota de voz).",
        "btn_confirm": "✅ Confirmar",
        "btn_correct": "✏️ Corregir",
        "btn_cancel": "❌ Cancelar",
        "ask_correction": "Dime qué hay que cambiar (texto o nota de voz).",
        "correction_limit": "Hemos llegado al límite de correcciones por chat. Revisa el informe en el panel.",
        "missing_fields": "Me faltan estos datos para completar el informe:\n{fields}\n\nEnvíamelos en un texto o una nota de voz.",
        "missing_fields_limit": "Siguen faltando datos obligatorios. Complétalos en el panel.",
        "cancelled": "Informe cancelado.",
        "superseded": "He cancelado el informe anterior y empiezo uno nuevo con tu mensaje.",
        "rejected": "Tu informe ha sido rechazado en la revisión.",
        "rejected_reason": "Tu informe ha sido rechazado en la revisión. Motivo: {reason}",
        # outcomes
        "delivered": "Tu {doc_type} está listo.",
        "failure": "Lo siento, no he podido generar tu informe. Inténtalo de nuevo o contacta con soporte.",
        "interrupted": "Lo siento, tu informe no ha terminado (el servicio se interrumpió). Envíalo de nuevo, por favor.",
        "email_subject": "{doc_type} — {date}",
        "email_body": "Adjunto encontrarás el informe «{doc_type}».",
        "email_reply_subject": "Re: {subject}",
        "report": "Informe",
        # emails from the panel
        "invite_subject": "{company}: tu acceso a ReportAI",
        "invite_body": "Hola, {name}:\n\n{company} te ha dado acceso a su panel de ReportAI. Elige tu contraseña aquí (el enlace caduca en 7 días):\n\n{link}",
        "reset_subject": "Restablece tu contraseña de ReportAI",
        "reset_body": "Para elegir una contraseña nueva, abre este enlace (caduca en 1 hora):\n\n{link}\n\nSi no lo has pedido tú, ignora este mensaje.",
        # values in summaries
        "yes": "Sí",
        "no": "No",
        "none": "—",
    },
    "en": {
        "rejected_sender": "Sorry, you don't have access to this channel. Ask your administrator for an invitation link, or give them this id: {sender}",
        "enrolled": "Hi {name}! You can now send me your reports: a voice note or a text with the details, and photos if needed.",
        "welcome": "Send me a voice note or a text with the report details (and photos if needed) and I'll prepare the document.",
        "rate_limited": "You've reached the hourly report limit. Please try again later.",
        "spend_capped": "The service has reached its daily usage cap. Please try again tomorrow.",
        "busy": "I'm still processing your previous report. I'll message you as soon as it's done.",
        "empty_message": "I couldn't understand that message. Send me a voice note or a text with the report details.",
        "unsupported_message": "I can't use that kind of message yet. Send a voice note, a text or a photo.",
        "not_configured": "This service isn't set up yet. Please let your administrator know.",
        "voice_not_configured": "Voice notes aren't enabled yet. Please send me the report as text.",
        "photo_attached": "📎 Photo added to the report.",
        "photo_without_report": "I saved the photo. Send the voice note or text for the report and I'll attach it.",
        "photo_failed": "I couldn't download the photo. Please send it again.",
        "doctype_prompt": "Which document type do you want to generate?",
        "doctype_unclear": "I didn't recognise that type. Pick one from the list.",
        "approval_header": "Here's what I extracted for your {doc_type}:",
        "approval_footer": "Confirm to generate the document, or tell me what to fix (text or voice note).",
        "btn_confirm": "✅ Confirm",
        "btn_correct": "✏️ Correct",
        "btn_cancel": "❌ Cancel",
        "ask_correction": "Tell me what to change (text or voice note).",
        "correction_limit": "We've hit the limit of corrections over chat. Please review the report in the panel.",
        "missing_fields": "I'm missing these details to complete the report:\n{fields}\n\nSend them in a text or a voice note.",
        "missing_fields_limit": "Required details are still missing. Please complete them in the panel.",
        "cancelled": "Report cancelled.",
        "superseded": "I cancelled the previous report and I'm starting a new one with your message.",
        "rejected": "Your report was rejected in review.",
        "rejected_reason": "Your report was rejected in review. Reason: {reason}",
        "delivered": "Your {doc_type} is ready.",
        "failure": "Sorry, we couldn't generate your report. Please try again or contact support.",
        "interrupted": "Sorry, your report didn't finish (the service was interrupted). Please send it again.",
        "email_subject": "{doc_type} — {date}",
        "email_body": "Attached is the report «{doc_type}».",
        "email_reply_subject": "Re: {subject}",
        "report": "Report",
        "invite_subject": "{company}: your access to ReportAI",
        "invite_body": "Hi {name},\n\n{company} has given you access to its ReportAI panel. Choose your password here (the link expires in 7 days):\n\n{link}",
        "reset_subject": "Reset your ReportAI password",
        "reset_body": "To choose a new password, open this link (it expires in 1 hour):\n\n{link}\n\nIf you didn't ask for it, ignore this message.",
        "yes": "Yes",
        "no": "No",
        "none": "—",
    },
}


def normalize_language(language: str | None) -> str:
    code = (language or DEFAULT_LANGUAGE).lower()[:2]
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def t(language: str | None, key: str, **values: object) -> str:
    """Looks `key` up in `language` (unknown languages fall back to Spanish); an unknown key
    is a programming error and raises."""
    return _MESSAGES[normalize_language(language)][key].format(**values)


def catalog(language: str) -> dict[str, str]:
    return _MESSAGES[language]


def format_date(language: str | None, value: date) -> str:
    return value.strftime("%d/%m/%Y") if normalize_language(language) == "es" else value.isoformat()


def format_time(value: time) -> str:
    return value.strftime("%H:%M")


def humanize_key(key: str) -> str:
    """'action_items' -> 'Action items': the label of a field nobody gave one."""
    text = key.replace("_", " ").strip()
    return text[:1].upper() + text[1:]
