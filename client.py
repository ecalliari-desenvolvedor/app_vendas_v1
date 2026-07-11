from functools import wraps
from flask import Flask, jsonify, redirect, render_template, request, flash, session, url_for
import requests
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# --- CONFIGURAÇÕES ---
#BACKEND_URL = 'http://127.0.0.1:5000'
BACKEND_URL = os.getenv('BACKEND_URL', 'http://127.0.0.1:5000')


# --- FUNÇÕES AUXILIARES ---
def contexto_index():
    user_data = session.get('user_data', {})
    return {
        'nome': user_data.get('nome', 'Usuário'),
        'permissoes': user_data.get('permissoes', {}),
        'empresas': user_data.get('empresas', []),
        'empresa_ativa': user_data.get('empresa_ativa', ''),
        'is_admin': user_data.get('is_admin', False),
    }

def usuario_tem_permissao(chave):
    user_data = session.get('user_data', {})
    if not user_data:
        return False
    if user_data.get('is_admin'):
        return True
    return bool(user_data.get('permissoes', {}).get(chave, False))

def api_request(method, endpoint, **kwargs):
    """Centraliza as chamadas ao backend, tratamento de erros e parse de JSON."""
    url = f"{BACKEND_URL}/{endpoint.lstrip('/')}"
    kwargs.setdefault('timeout', 15) # Timeout padrão
    
    try:
        resposta = requests.request(method, url, **kwargs)
        is_json = resposta.headers.get('Content-Type', '').startswith('application/json')
        dados = resposta.json() if is_json else {}
        return resposta.status_code, dados, resposta.text if not is_json else None
    except requests.RequestException as e:
        return 503, {'erro': f'Servidor indisponível: {str(e)}'}, None


# --- DECORADORES ---
def auth_required(is_api=False):
    """Verifica se o usuário está logado."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_data' not in session:
                if is_api:
                    return jsonify({'erro': 'Usuário não autenticado'}), 401
                flash('Por favor, faça login para acessar esta página.', 'error')
                return render_template('login_cadastro.html', error='Faça login para acessar.')
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def permission_required(chave, is_api=False):
    """Verifica se o usuário possui uma permissão específica."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not usuario_tem_permissao(chave):
                if is_api:
                    return jsonify({'erro': f'Sem permissão ({chave})'}), 403
                flash('Você não possui permissão para esta ação.', 'error')
                return render_template('index.html', **contexto_index())
            return f(*args, **kwargs)
        return decorated_function  # <-- CORRIGIDO AQUI (antes estava 'return decorator')
    return decorator

def admin_required(is_api=False):
    """Verifica se o usuário é administrador."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('user_data', {}).get('is_admin', False):
                if is_api:
                    return jsonify({'erro': 'Apenas administrador pode acessar.'}), 403
                flash('Acesso restrito para administradores.', 'error')
                return render_template('index.html', **contexto_index())
            return f(*args, **kwargs)
        return decorated_function  # <-- CORRIGIDO AQUI (antes estava 'return decorator')
    return decorator


# --- ROTAS ---
@app.route('/')
def home():
    if 'user_data' in session:
        return render_template('index.html', **contexto_index())
    return render_template('home.html')

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar():
    if request.method == 'GET':
        return render_template('login_cadastro.html')

    payload = {
        'nome': request.form['nome'],
        'email': request.form['email'],
        'celular': request.form['celular'],
        'cnpj': request.form['cnpj'],
        'senha': request.form['senha'],
        'empresas': request.form.getlist('empresas'),
        'perm_download_tabelas': 'perm_download_tabelas' in request.form,
        'perm_fazer_pedido': 'perm_fazer_pedido' in request.form,
        'perm_solicitar_visita': 'perm_solicitar_visita' in request.form,
        'perm_visualizar_pedidos': 'perm_visualizar_pedidos' in request.form,
    }

    status, dados, _ = api_request('POST', 'adicionar', json=payload)

    if status >= 400:
        erro = dados.get('erro', 'Erro ao cadastrar usuário.')
        flash(erro, 'error')
        return render_template('login_cadastro.html', error=erro)

    if not dados:
        flash('Resposta inválida do servidor.', 'error')
        return render_template('login_cadastro.html', error='Resposta inválida do servidor.')

    session['user_data'] = dados
    return render_template('index.html', **contexto_index())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login_cadastro.html')

    payload = {
        'email': request.form['email'],
        'cnpj': request.form['cnpj'],
        'senha': request.form['senha']
    }

    status, dados, texto = api_request('POST', 'login', json=payload)

    if status != 200:
        erro = dados.get('erro', texto or 'Erro no login.')
        flash(erro, 'error')
        return render_template('login_cadastro.html', error=erro)

    session['user_data'] = dados
    return render_template('index.html', **contexto_index())

@app.route('/logout')
def logout():
    session.pop('user_data', None)
    return redirect(url_for('home'))

@app.route('/agendar', methods=['GET', 'POST'])
@auth_required(is_api=False)
@permission_required('solicitar_visita', is_api=False)
def agendar():
    if request.method == 'GET':
        return render_template('index.html', **contexto_index())

    payload = {
        'usuario_id': session['user_data']['id'],
        'data_hora': request.form['data'],
        'observacao': request.form['observacoes'],
    }

    status, dados, _ = api_request('POST', 'adicionaragenda', json=payload)

    if status == 409:
        flash('Já existe um agendamento para este dia e hora.', 'error')
    elif status >= 400:
        flash(dados.get('erro', 'Erro ao agendar visita.'), 'error')
    else:
        flash('Agendamento realizado com sucesso!', 'success')
    
    return render_template('index.html', **contexto_index())

@app.route('/carregar_produtos', methods=['GET'])
@auth_required(is_api=True)
@permission_required('download_tabelas', is_api=True)
def carregar_produtos():
    params = {
        'empresa': session['user_data'].get('empresa_ativa', 'Varejo'),
        'usuario_id': session['user_data'].get('id')
    }
    status, dados, _ = api_request('GET', 'carregar_produtos', params=params, timeout=60)
    
    if status in (502, 503):
        return jsonify(dados), status
        
    return jsonify(dados if dados else {'erro': 'Resposta inválida do servidor'}), status

@app.route('/atualizar_tabelas', methods=['POST'])
@auth_required(is_api=False)
@admin_required(is_api=False)
def atualizar_tabelas():
    empresa = request.form.get('empresa_arquivo', '').strip()
    arquivo = request.files.get('arquivo_tabela')

    if not empresa:
        flash('Selecione a empresa para atualização.', 'error')
        return render_template('index.html', **contexto_index())

    if arquivo is None or not arquivo.filename:
        flash('Selecione um arquivo .xlsx para atualizar.', 'error')
        return render_template('index.html', **contexto_index())

    files = {
        'arquivo_tabela': (arquivo.filename, arquivo.stream, arquivo.mimetype or 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    data = {'usuario_id': session['user_data']['id'], 'associacao': empresa}

    status, dados, _ = api_request('POST', 'atualizar_tabelas', data=data, files=files, timeout=120)

    if status >= 400:
        flash(dados.get('erro', 'Erro ao atualizar tabela.'), 'error')
    else:
        flash(dados.get('mensagem', 'Tabela atualizada com sucesso!'), 'success')
        
    return render_template('index.html', **contexto_index())

@app.route('/dados_mapa_vendas', methods=['GET'])
@auth_required(is_api=True)
@admin_required(is_api=True)
def dados_mapa_vendas():
    params = {'usuario_id': session['user_data']['id']}
    
    if data_inicio := request.args.get('data_inicio', '').strip():
        params['data_inicio'] = data_inicio
    if data_fim := request.args.get('data_fim', '').strip():
        params['data_fim'] = data_fim

    status, dados, _ = api_request('GET', 'dados_mapa_vendas', params=params, timeout=180)
    
    if status in (502, 503):
        return jsonify(dados), status

    return jsonify(dados if dados else {'erro': 'Resposta inválida do servidor'}), status

@app.route('/salvar_pedido', methods=['POST'])
@auth_required(is_api=True)
@permission_required('fazer_pedido', is_api=True)
def salvar_pedido():
    dados_req = request.get_json(silent=True) or {}
    payload = {
        'usuario_id': session['user_data']['id'],
        'itens': dados_req.get('itens', [])
    }

    status, dados, _ = api_request('POST', 'salvar_pedido', json=payload)

    if status in (502, 503):
        return jsonify(dados), status

    if aviso_email := dados.get('aviso_email'):
        flash(aviso_email, 'warning')

    return jsonify(dados if dados else {'erro': 'Resposta inválida do servidor'}), status

@app.route('/meus_pedidos', methods=['GET'])
@auth_required(is_api=True)
@permission_required('visualizar_pedidos', is_api=True)
def meus_pedidos():
    usuario_id = session['user_data']['id']
    status, dados, _ = api_request('GET', f'pedidos_usuario/{usuario_id}', timeout=60)

    if status in (502, 503):
        return jsonify(dados), status

    return jsonify(dados if dados else {'erro': 'Resposta inválida do servidor'}), status

@app.route('/meus_pedidos/<int:pedido_id>/itens', methods=['GET'])
@auth_required(is_api=True)
@permission_required('visualizar_pedidos', is_api=True)
def itens_meu_pedido(pedido_id):
    usuario_id = session['user_data']['id']
    status, dados, _ = api_request('GET', f'pedido/{pedido_id}/itens', params={'usuario_id': usuario_id}, timeout=60)

    if status in (502, 503):
        return jsonify(dados), status

    return jsonify(dados if dados else {'erro': 'Resposta inválida do servidor'}), status

@app.route('/selecionar_empresa', methods=['POST'])
@auth_required(is_api=False)
def selecionar_empresa():
    payload = {
        'usuario_id': session['user_data']['id'],
        'empresa': request.form.get('empresa_ativa', '')
    }

    status, dados, texto = api_request('POST', 'selecionar_empresa', json=payload)

    if status != 200:
        erro = dados.get('erro', texto or 'Erro ao trocar empresa.')
        flash(erro, 'error')
    else:
        session['user_data'] = dados
        flash('Empresa ativa alterada com sucesso.', 'success')

    return render_template('index.html', **contexto_index())

if __name__ == '__main__':
    app.run(port=5001, debug=True, host='0.0.0.0', use_reloader=False)