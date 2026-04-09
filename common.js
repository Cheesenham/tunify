const SESSION_ID = localStorage.getItem('MPL_USER_ID');
const BASE_URL = localStorage.getItem('MPL_BASE_URL') || window.location.origin;

function checkAuth() {
    if (!SESSION_ID) {
        window.location.href = "/"; // If not at root, redirect to login
        return false;
    }
    return true;
}

function logout() {
    localStorage.removeItem('MPL_USER_ID');
    localStorage.removeItem('MPL_BASE_URL');
    window.location.href = "/";
}

async function apiFetch(path, options = {}) {
    if (!options.headers) options.headers = {};
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(options.body);
    }
    const res = await fetch(`${BASE_URL}${path}`, options);
    return await res.json();
}
