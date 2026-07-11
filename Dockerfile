# Usa uma imagem oficial leve do Python
FROM python:3.13.1-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia o arquivo de dependências para o container
COPY requirements.txt .

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código do projeto para o container
COPY . .

# Expõe a porta que o Flask vai usar
EXPOSE 5001

# Comando para iniciar a aplicação
CMD ["python", "app.py"]
