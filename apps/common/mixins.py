"""apps/common/mixins.py — Mixins reutilizables para vistas Django."""


class WithCreateFormMixin:
    """
    Inyecta `create_form` (instancia vacía) en el contexto de una ListView.
    Permite renderizar el formulario de alta directamente en la misma página
    (modal de creación) sin necesitar una vista ni URL separadas.

    Uso:
        class ClienteListView(WithCreateFormMixin, ListView):
            form_class = ClienteForm
            ...
    """
    form_class = None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.form_class:
            ctx["create_form"] = self.form_class()
        return ctx
