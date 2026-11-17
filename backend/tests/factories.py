"""Test data factories. Fictional people only; never real customer data."""

import factory

from app.modules.identity.models import User


class UserFactory(factory.Factory):  # type: ignore[misc]
    class Meta:
        model = User

    user_type = "human"
    email = factory.Sequence(lambda n: f"user{n}@example.test")
    full_name = factory.Faker("name")
    locale = "en"
    is_active = True
    auth_provider = "local"
    failed_login_count = 0
