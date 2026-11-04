const MEDINRIAWEB_URL = 'http://127.0.0.1:9000';
const MENU_ITEM_ID = 'medinriaweb-menu-item';
const MAX_RETRIES = 10;
let retryCount = 0;

function addMedInriaWebNavButton() {
    const globalNav = document.querySelector('.g-global-nav');
    if (!globalNav) {
        if (retryCount < MAX_RETRIES) {
            retryCount++;
            setTimeout(addMedInriaWebNavButton, 500);
        }
        return;
    }

    if (document.getElementById(MENU_ITEM_ID)) {
        return;
    }

    const listItem = document.createElement('li');
    listItem.className = 'g-global-nav-li';
    listItem.id = MENU_ITEM_ID;

    const link = document.createElement('a');
    link.className = 'g-nav-link';
    link.href = MEDINRIAWEB_URL;
    link.target = '_blank';
    link.innerHTML = '<i class="icon-picture"></i><span>MedInriaWeb</span>';

    link.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        window.open(MEDINRIAWEB_URL, '_blank');
    });

    listItem.appendChild(link);
    globalNav.appendChild(listItem);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', addMedInriaWebNavButton);
} else {
    addMedInriaWebNavButton();
}
