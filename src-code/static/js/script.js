document.getElementById('verificarCodigoPostal').addEventListener('click', function() {
    const postalCode = document.getElementById('postalCodeInput').value.trim();

    if (!postalCode) {
        document.getElementById('resultado').innerText = 'Por favor, insira um código postal.';
        return;
    }

    fetch('/verify_postal_code', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ postal_code: postalCode })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errData => {
                throw new Error(errData.message || 'Erro na requisição');
            });
        }
        return response.json();
    })
    .then(data => {
        document.getElementById('resultado').innerText = data.message;
        document.getElementById('resultado').classList.add('success');
        document.getElementById('resultado').classList.remove('error');
    })
    .catch(error => {
        console.error('Erro de rede ou servidor:', error);
        document.getElementById('resultado').innerText = 'Erro: ' + error.message;
        document.getElementById('resultado').classList.add('error');
        document.getElementById('resultado').classList.remove('success');
    })
    .finally(() => {
        document.getElementById('postalCodeInput').value = '';
    });
});
