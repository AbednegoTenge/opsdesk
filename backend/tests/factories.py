import factory

from apps.users.models import Role, User

DEFAULT_PASSWORD = "Sup3r-Secret-Pass!"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")
    role = Role.VIEWER
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or DEFAULT_PASSWORD)
        if create:
            self.save(update_fields=["password"])


class IncidentFactory(factory.django.DjangoModelFactory):
    """Creates incidents through the service layer so events and due times are realistic."""

    class Meta:
        model = "incidents.Incident"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        from apps.incidents import services

        status = kwargs.pop("status", None)
        incident = services.create_incident(
            actor=kwargs.pop("reporter", None) or UserFactory(role=Role.ENGINEER),
            title=kwargs.pop("title", "Database latency spike"),
            description=kwargs.pop("description", ""),
            priority=kwargs.pop("priority", "medium"),
            assignee=kwargs.pop("assignee", None),
        )
        if kwargs:
            model_class.objects.filter(pk=incident.pk).update(**kwargs)
        if status:
            model_class.objects.filter(pk=incident.pk).update(status=status)
        incident.refresh_from_db()
        return incident
