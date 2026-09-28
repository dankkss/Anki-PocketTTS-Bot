# Anki-PocketTTS-Bot 🎙️⚡

Bot no Telegram para geração sob demanda de arquivos de áudio `.mp3` de alta qualidade, otimizados para cartões e flashcards do **Anki**.

---

## 💡 Recursos Principais

1. **Motor Edge-TTS (Microsoft):**
   - Mais de 400 vozes de estúdio com pronúncia nativa em mais de 100 idiomas (Português, Inglês US/UK, Espanhol, Francês, Japonês, Alemão, etc.).
   - Geração instantânea (< 1 segundo).
   - Ajuste de velocidade calibrado para aprendizado de idiomas: `0.8x` (lento/foco auditivo), `1.0x` (normal) e `1.2x` (rápido).

2. **Motor Pocket TTS (Kyutai):**
   - Clonagem zero-shot de voz a partir de áudios curtos de 5 a 10 segundos enviados diretamente pelo Telegram.
   - Salvamento e exportação de perfis comprimidos em `.safetensors`.
   - Síntese de novas frases com a voz clonada (ideal para imitar a voz de professores, falantes nativos específicos ou podcasts).

3. **Arquitetura Nuvem Econômica (Render Webhook - Opção A):**
   - Roda como Web Service em container Docker otimizado para CPU.
   - Atende via Webhook assíncrono sob demanda, economizando a cota mensal gratuita de 750h compartilhadas do Render (dorme quando ocioso e não consome horas).

---

## 📱 Como Usar no Telegram (@dankkss_ankitts_bot)

- **Gerar áudio de texto:** Envie qualquer palavra ou frase. O bot responde imediatamente com o arquivo `.mp3` com título e tags prontas para o Anki.
- **Clonar uma voz:** Grave um áudio pelo microfone ou envie um arquivo de áudio (5 a 10s) e depois responda a ele com `/clonar <nome>` (ou simplesmente envie `/clonar <nome>` logo após enviar o áudio).
- **Selecionar vozes:** Digite `/vozes` para escolher entre vozes de estúdio (Edge-TTS) e perfis clonados (Pocket TTS).
- **Ajustar ritmo:** Digite `/velocidade` para selecionar 0.8x, 1.0x ou 1.2x.
- **Ver status:** Digite `/status` para checar as preferências ativas e perfis salvos.

---

## 🗂️ Como Importar no Anki

1. No Telegram, clique nos três pontinhos do arquivo `.mp3` gerado e selecione **Compartilhar** ou **Salvar**.
2. **No Anki Desktop:** Arraste o arquivo `.mp3` diretamente para o campo de pronúncia/áudio do seu cartão (ou coloque na pasta `collection.media`).
3. **No AnkiMobile (iOS) ou AnkiDroid:** Use o menu de anexo do cartão e selecione o arquivo baixado.

---

## 🚀 Deploy no Render (Opção A)

1. Crie um **Web Service** no Render conectando o repositório GitHub `dankkss/Anki-PocketTTS-Bot`.
2. O Render detectará automaticamente o `Dockerfile` ou blueprint `render.yaml`.
3. Configure as variáveis de ambiente no painel do Render:
   - `BOT_TOKEN`: Token oficial fornecido pelo @BotFather.
   - `WEBHOOK_URL`: `https://seu-servico.onrender.com`
   - `SECRET_TOKEN`: Token alfanumérico para proteção contra requisições forjadas.
4. Após o primeiro deploy bem-sucedido, ative o webhook chamando o endpoint:
   ```bash
   curl -X POST "https://seu-servico.onrender.com/set_webhook"
   ```
5. Verifique o status com:
   ```bash
   curl "https://seu-servico.onrender.com/health"
   ```

---

## 🔒 Segurança e Privacidade (Zero-Secrets)

Este repositório adota rigorosamente a política Zero-Secrets:
- Nenhum token, credencial real ou dado pessoal reside no código versionado.
- Tokens reais são injetados via variáveis de ambiente no container ou lidos de `/root/.config/anki-tts-bot/config.json`.
