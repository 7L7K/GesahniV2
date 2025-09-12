#!/usr/bin/env python3

import sys

sys.path.insert(0, '/Users/kingal/2025/GesahniV2')

import random
import string

from fastapi.testclient import TestClient

from app.main import app


def _generate_unique_username():
    return 'test_logout_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def main():
    client = TestClient(app)

    # Register and login
    username = _generate_unique_username()
    password = 'secret123'

    print('Registering user...')
    register_resp = client.post('/v1/auth/register', json={'username': username, 'password': password})
    print(f'Register: {register_resp.status_code}')

    print('Logging in...')
    login_resp = client.post('/v1/auth/login', json={'username': username, 'password': password})
    print(f'Login: {login_resp.status_code}')

    print('Getting CSRF token...')
    csrf_resp = client.get('/v1/auth/csrf')
    print(f'CSRF: {csrf_resp.status_code}')
    csrf_token = None
    if csrf_resp.status_code == 200:
        csrf_token = csrf_resp.json().get('csrf_token')
        print(f'CSRF token: {csrf_token[:20]}...')

    print('Testing logout without CSRF...')
    logout_resp = client.post('/v1/auth/logout')
    print(f'Logout without CSRF: {logout_resp.status_code} - {logout_resp.text}')

    print('Re-logging in...')
    login_resp2 = client.post('/v1/auth/login', json={'username': username, 'password': password})
    print(f'Login 2: {login_resp2.status_code}')

    print('Testing logout with CSRF...')
    if csrf_token:
        logout_with_csrf_resp = client.post('/v1/auth/logout', headers={'X-CSRF-Token': csrf_token})
        print(f'Logout with CSRF: {logout_with_csrf_resp.status_code} - {logout_with_csrf_resp.text}')
    else:
        print('No CSRF token available')

if __name__ == '__main__':
    main()
