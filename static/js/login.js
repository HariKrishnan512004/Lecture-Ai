document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    const errorMessage = document.getElementById('errorMessage');
    const loginBtn = document.querySelector('.login-btn');
    const splashScreen = document.getElementById('splashScreen');

    // Hide splash after 3 seconds
    setTimeout(() => {
        splashScreen.style.display = 'none';
    }, 3000);

    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value.trim();

        errorMessage.classList.remove('show');
        errorMessage.textContent = '';

        if (!username || !password) {
            showError('Please fill in all fields');
            return;
        }

        loginBtn.classList.add('loading');

        try {
            const response = await fetch('/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username: username,
                    password: password
                })
            });

            if (response.ok) {
                // Store in session storage
                sessionStorage.setItem('loggedIn', 'true');
                sessionStorage.setItem('username', username);

                loginBtn.innerHTML = '<span>✓ Success!</span>';
                loginBtn.style.background = 'linear-gradient(135deg, #00d4ff 0%, #00ff88 100%)';

                setTimeout(() => {
                    window.location.href = '/dashboard';
                }, 1000);
            } else {
                loginBtn.classList.remove('loading');
                showError('Invalid username or password');
                loginForm.reset();
            }
        } catch (error) {
            loginBtn.classList.remove('loading');
            showError('Login error: ' + error.message);
        }
    });

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.classList.add('show');
        setTimeout(() => {
            errorMessage.classList.remove('show');
        }, 5000);
    }
});