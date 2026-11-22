from django.core.paginator import Paginator


def paginar(request, itens, por_pagina):
    """Devolve a página pedida em ?pagina=N. Número inválido cai na primeira página e número
    alto demais, na última, em vez de responder com erro."""
    return Paginator(itens, por_pagina).get_page(request.GET.get("pagina"))


def filtros_da_url(request):
    """Os parâmetros da URL sem o número da página, para os links de paginação manterem a busca."""
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return parametros.urlencode()
