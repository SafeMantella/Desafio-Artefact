# NÃO TRIVIAL: devolução aplicando política + dados do pedido


_Modelo: qwen/qwen3.8-27b. Gerado por `run_examples.py`._


**Cliente:** Comprei um ukulele aí e me arrependi. É o pedido 7, consigo devolver?

> 🔧 chama `consultar_politica(topico='política de devolução e arrependimento')`

> 🔧 `consultar_politica` →
>
> ## 4. Política de Trocas e Devoluções
> 
> Segue o Código de Defesa do Consumidor (Lei nº 8.078/90).
> 
> ### 4.1 Direito de arrependimento (compras online)
> - Devolução em até **7 (sete) dias corridos** após o recebimento do produto, sem necessidade de justificativa.
> - Produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais.
> - Reembolso na mesma forma de pagamento original em até 10 dias úteis.
> - Frete de devolução por conta da loja em caso de arrependimento.
> 
> ### 4.2 Trocas por defeito
> - Defeito de fabricação: troca em até **30 (trinta) dias corridos** após a compra.
> - Após 30 dias: acionar a garantia diretamente com o fabricante. A loja pode intermediar mediante solicitação.
> - Não cobre danos por mau uso, quedas, umidade excessiva ou modificações não autorizadas.
> 
> ### 4.3 Trocas por preferência
> - Preferência (cor, modelo, tamanho): permitidas em até **7 dias**, mediante disponibilidade do produto desejado.
> - Produto em perfeito estado e na embalagem original.
> - Di […]

**Assistente:** Claro, sem problema! Pra eu consultar o pedido 7, preciso confirmar sua identidade: me passa seu **e-mail** ou **nome e sobrenome**, por favor?

E já adiantando: o direito de arrependimento vale por **7 dias corridos a partir do recebimento** — então, quando você me der esses dados, também me diz **quando recebeu o ukulele** que eu já te digo se dá tempo de devolver. 🎶

**Cliente:** Letícia Gonçalves Rocha

> 🔧 chama `status_pedido(order_id=7, identificador='Letícia Gonçalves Rocha')`

> 🔧 `status_pedido` →
>
> Pedido 7 — entregue
> Cliente: Letícia Gonçalves Rocha
> Data do pedido: 03/02/2026 (há 50 dias da compra; hoje = 25/03/2026)
> Itens: 1x Shelby SU-21S Soprano Sunburst
> Valor total: R\$ 159,90  ·  Pagamento: cartão de crédito em 3x
> Previsão de entrega: 17/02/2026
> Código de rastreio: BRKR1122334BR
> Obs.: o sistema NÃO registra a data de recebimento, só a da compra. Se o prazo da política contar a partir do recebimento, pergunte ao cliente quando ele recebeu antes de dizer se está dentro ou fora do prazo.

**Assistente:** Oi, Letícia! Encontrei seu pedido: **Shelby SU-21S Soprano Sunburst** por R\$ 159,90, pago em 3x no cartão. O status está como entregue, com previsão de entrega em 17/02/2026.

Só falta um detalhe: o prazo de arrependimento é de **7 dias corridos a partir do recebimento**, e o sistema não registra a data exata em que você recebeu. Me conta: **em que data você recebeu o ukulele?** Com isso eu te digo se ainda dá tempo de devolver. 🎶

**Cliente:** Recebi ele ontem.

**Assistente:** Perfeito, Letícia! Se você recebeu ontem (24/03), está **dentro do prazo de 7 dias** — pode devolver sim! ✅

Só precisa garantir:
- Ukulele na **embalagem original**, sem sinais de uso, com todos os acessórios e manuais;
- O **reembolso** vai para o mesmo cartão de crédito, em até 10 dias úteis;
- O **frete de devolução é por nossa conta**.

Me avisa quando quiser que eu te oriento sobre o próximo passo. E, se mudar de ideia, o ukulele é um bichinho lindo — vale a pena uma chance com ele também 😄
