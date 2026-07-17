# QRCodex MVP

App web em Python + Flask para criar QR Codes com redirecionamento contado e planos por limite de visitas.

## O que já vem pronto

- Cadastro e login de usuários.
- Escolha de plano no cadastro.
- Admin dashboard.
- CRUD de planos com liberdade total:
  - nome;
  - preço/rótulo;
  - limite diário de redirecionamentos;
  - limite mensal de redirecionamentos;
  - quantidade máxima de QR Codes;
  - plano público/oculto;
  - plano ativo/inativo;
  - plano padrão.
- CRUD de QR Codes pelo usuário.
- QR Code em PNG gerado sem Pillow, usando PyPNG puro.
- Link público no formato `/q/slug`.
- Contagem de visitas permitidas e bloqueadas.
- Bloqueio automático quando o plano atingir limite diário/mensal.
- Admin pode alterar plano, ativar/desativar usuário e liberar admin.
- Configuração para abrir/fechar novos cadastros.
- Bootstrap com visual leve, bordas arredondadas e cores relaxantes.

## Como rodar no Windows

### Opção rápida

Dê dois cliques em:

```bat
rodar_tudo.bat
```

Ele cria o `.venv`, instala dependências e abre:

```txt
http://localhost:5432
```

### Opção manual

```bat
instalar.bat
rodar.bat
```


## Correção importante desta versão

Esta versão removeu a dependência do Pillow. O QR Code agora é gerado com `qrcode + pypng`, o que evita aquele erro chato no Windows/Python 3.14 tentando compilar Pillow e reclamando de `zlib`.

Se você já tentou instalar a versão anterior e ficou uma `.venv` quebrada, apague a pasta `.venv` dentro do projeto e rode novamente:

```bat
rodar_tudo.bat
```

## Login admin inicial

```txt
E-mail: admin@qrcodex.local
Senha: 000000
```

Você pode mudar isso no arquivo `.env` antes da primeira execução:

```env
ADMIN_EMAIL=admin@qrcodex.local
ADMIN_PASSWORD=000000
SECRET_KEY=troque-esta-chave-em-producao
FLASK_PORT=5432
```

> Importante: se o banco já foi criado, trocar `ADMIN_PASSWORD` no `.env` não muda a senha do admin existente. Para zerar tudo, use `resetar_banco.bat`.

## Como funciona o redirecionamento

1. O usuário cria um QR Code apontando para uma URL final.
2. O QR Code gerado aponta para o link do QRCodex, por exemplo:

```txt
http://localhost:5432/q/cardapio
```

3. Quando alguém acessa esse link:
   - o sistema verifica se o QR está ativo;
   - verifica o plano do dono do QR;
   - conta visitas do dia/mês;
   - se estiver dentro do limite, registra a visita e redireciona;
   - se passou do limite, registra tentativa bloqueada e mostra página de limite atingido.

## Onde fica o banco

SQLite local:

```txt
instance/qrcodex.db
```

ou `qrcodex.db`, dependendo da URI configurada.

## Próximos passos recomendados

- Integrar pagamento real: Mercado Pago, Stripe ou Asaas.
- Criar tabela de compras/assinaturas separada do plano.
- Adicionar domínio customizado por cliente.
- Criar analytics por país/dispositivo/campanha.
- Adicionar exportação CSV.
- Gerar QR Codes com logo e cores.
- Transformar em PWA para instalar como app no Android.

## Estrutura

```txt
qrcodex_mvp/
  app.py
  requirements.txt
  .env.example
  instalar.bat
  rodar.bat
  rodar_tudo.bat
  resetar_banco.bat
  templates/
  static/
```
