import logging
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AccountEmailIdentity
from .services import normalize_email

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def sync_account_email_identity(sender, instance, created, **kwargs):
    """Đảm bảo mọi đường ghi User có email đều được đồng bộ AccountEmailIdentity an toàn."""
    if not instance.email:
        return
    norm = normalize_email(instance.email)
    try:
        identity = AccountEmailIdentity.objects.get(user=instance)
        if identity.normalized_email != norm:
            identity.normalized_email = norm
            identity.reset_verification()
            identity.token_version += 1
            identity.save(update_fields=["normalized_email", "verified_at", "token_version", "updated_at"])
    except AccountEmailIdentity.DoesNotExist:
        AccountEmailIdentity.objects.create(
            user=instance,
            normalized_email=norm,
            verified_at=None,
        )
