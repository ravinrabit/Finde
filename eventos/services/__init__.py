"""Regras de negócio que não pertencem nem à view nem ao model.

Views cuidam de HTTP; models cuidam de dados; o que envolve mais de um passo,
transação ou decisão de negócio mora aqui e é testável sem cliente HTTP.
"""
