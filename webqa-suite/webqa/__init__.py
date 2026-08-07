"""WebQA Suite — biblioteca de apoio para os testes genéricos de qualidade web."""
# Fonte ÚNICA da versão (pyproject.toml, tool.setuptools.dynamic). A ponta anda À
# FRENTE da última release publicada em releases/: cortada a tag v1.0.0, deixar
# `main` em "1.0.0" faria dois conteúdos distintos — o taggeado e este — produzirem
# wheels com o mesmo número, e a comparabilidade de laudos que a versão existe para
# dar deixaria de valer sem nada ficar vermelho. tests/test_release.py cobra.
__version__ = "1.1.0.dev0"
