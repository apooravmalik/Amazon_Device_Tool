// frontend/app.js

document.addEventListener('DOMContentLoaded', () => {
    App.initialize();
});

const App = {
    // 1. Configuration and State
    API_BASE_URL: 'http://127.0.0.1:8000/api',
    BUILD_PAGE_SIZE: 100,
    allBuildings: [],
    selectedBuildingId: null,

    // 2. Cached DOM Elements
    elements: {},

    // 3. Initialization Function
    initialize() {
        // Cache all DOM elements
        this.elements.buildingsContainer = document.getElementById('deviceList');
        this.elements.loader = document.getElementById('loader');
        this.elements.notification = document.getElementById('notification');
        this.elements.buildingSearch = document.querySelector('.building-search');
        this.elements.buildingDropdown = document.querySelector('.building-dropdown');
        this.elements.clearFilter = document.querySelector('.clear-filter');
        this.elements.ignoreModal = document.getElementById('ignoreModal');
        this.elements.modalTitle = document.getElementById('modalTitle');
        this.elements.modalItemList = document.getElementById('modalItemList');
        this.elements.modalConfirmBtn = document.getElementById('modalConfirmBtn');
        this.elements.modalCancelBtn = document.getElementById('modalCancelBtn');
        this.elements.closeButton = document.querySelector('.close-button');
        this.elements.modalSearch = document.getElementById('modalSearch');
        this.elements.modalSelectAllBtn = document.getElementById('modalSelectAllBtn');

        // Setup event listeners and load initial data
        this.setupBuildingSelector();
        this.loadAllBuildings();
    },

    // 4. Utility Methods (Child Functions)
    
    showNotification(text, isError = false, timeout = 3000) {
        const { notification } = this.elements;
        notification.textContent = text;
        notification.style.backgroundColor = isError ? '#ef4444' : '#333';
        notification.classList.add('show');
        setTimeout(() => notification.classList.remove('show'), timeout);
    },

    async apiRequest(endpoint, options = {}) {
        const url = `${this.API_BASE_URL}/${endpoint}`;
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Unknown error occurred' }));
                throw new Error(errorData.detail || `Request failed with status ${response.status}`);
            }
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.indexOf("application/json") !== -1) {
                return await response.json();
            }
            return {};
        } catch (error) {
            console.error(`API request to ${endpoint} failed:`, error);
            this.showNotification(error.message, true);
            throw error;
        }
    },

    escapeHtml(str) {
        return String(str || '').replace(/[&<>"']/g, s => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;',
            '"': '&quot;', "'": '&#39;'
        }[s]));
    },

    // 5. Building List & Search Logic
    
    setupBuildingSelector() {
        const { buildingSearch, buildingDropdown, clearFilter } = this.elements;

        buildingSearch.addEventListener('input', () => {
            const query = buildingSearch.value.toLowerCase();
            buildingDropdown.innerHTML = '';

            if (query.length === 0) {
                buildingDropdown.style.display = 'none';
                clearFilter.style.display = 'none';
                return;
            }

            const filtered = this.allBuildings.filter(b =>
                b.name.toLowerCase().includes(query)
            );

            if (filtered.length > 0) {
                filtered.forEach(building => {
                    const option = document.createElement('div');
                    option.className = 'building-option';
                    option.textContent = building.name;
                    option.addEventListener('click', () => this.selectBuilding(building));
                    buildingDropdown.appendChild(option);
                });
                buildingDropdown.style.display = 'block';
                clearFilter.style.display = 'block';
            } else {
                buildingDropdown.style.display = 'none';
            }
        });

        clearFilter.addEventListener('click', () => {
            buildingSearch.value = '';
            buildingDropdown.style.display = 'none';
            clearFilter.style.display = 'none';
            this.selectedBuildingId = null;
            this.loadAllBuildings();
        });

        document.addEventListener('click', (e) => {
            if (!buildingSearch.contains(e.target) && !buildingDropdown.contains(e.target)) {
                buildingDropdown.style.display = 'none';
            }
        });
    },

    selectBuilding(building) {
        const { buildingSearch, buildingDropdown, clearFilter } = this.elements;
        buildingSearch.value = building.name;
        buildingDropdown.style.display = 'none';
        this.selectedBuildingId = building.id;
        clearFilter.style.display = 'block';
        this.loadFilteredBuilding(building);
    },

    async loadFilteredBuilding(building) {
        const { buildingsContainer } = this.elements;
        buildingsContainer.innerHTML = '';
        const card = this.createBuildingCard(building);
        buildingsContainer.appendChild(card);
        await this.loadItemsForBuilding(card);
        const body = card.querySelector('.building-body');
        const toggleBtn = card.querySelector('.toggle-btn');
        body.style.display = 'block';
        toggleBtn.textContent = '-';
    },

    async loadAllBuildings() {
        const { loader, buildingsContainer } = this.elements;
        try {
            loader.style.display = 'block';
            this.allBuildings = await this.apiRequest('buildings');
            buildingsContainer.innerHTML = '';
            this.allBuildings.forEach(building => {
                buildingsContainer.appendChild(this.createBuildingCard(building));
            });
        } finally {
            loader.style.display = 'none';
        }
    },

    // 6. Building Card Logic
    
    createBuildingCard(building) {
        const card = document.createElement('div');
        card.className = 'building-card';
        card.dataset.buildingId = building.id;
        const startTime = building.start_time || '09:00';
        const endTime = building.end_time || '17:00';

        card.innerHTML = `
            <div class="building-header">
                <button class="toggle-btn">+</button>
                <h2 class="building-title">${this.escapeHtml(building.name)}</h2>
                <div class="building-actions">
                    <button class="bulk-btn bulk-disarm">Set Ignore Flags</button>
                </div>
                <div class="building-time-control">
                    <label>Start:</label>
                    <input type="time" class="time-input start-time-input" value="${startTime}" required />
                    <label>End:</label>
                    <input type="time" class="time-input end-time-input" value="${endTime}" required />
                    <button class="time-save-btn">Save</button>
                </div>
                <div class="building-status"></div>
            </div>
            <div class="building-body" style="display:none;">
                <div class="building-controls">
                    <input type="text" class="item-search" placeholder="Search proevents..."/>
                </div>
                <ul class="items-list"></ul>
                <div class="building-loader" style="display:none;">Loading...</div>
            </div>
        `;
        this.setupBuildingCardEvents(card);
        return card;
    },

    setupBuildingCardEvents(card) {
        const itemsList = card.querySelector('.items-list');
        const header = card.querySelector('.building-header');
        const body = card.querySelector('.building-body');
        const toggleBtn = card.querySelector('.toggle-btn');
        const startTimeInput = card.querySelector('.start-time-input');
        const endTimeInput = card.querySelector('.end-time-input');
        const timeSaveBtn = card.querySelector('.time-save-btn');
        const disarmBtn = card.querySelector('.bulk-disarm');
        const itemSearch = card.querySelector('.item-search');

        const toggleVisibility = async () => {
            const isHidden = body.style.display === 'none';
            body.style.display = isHidden ? 'block' : 'none';
            toggleBtn.textContent = isHidden ? '-' : '+';
            if (isHidden && itemsList.children.length === 0) {
                await this.loadItemsForBuilding(card);
            }
        };

        header.addEventListener('click', (e) => {
            if (!e.target.closest('.building-time-control') && !e.target.closest('.building-actions')) {
                toggleVisibility();
            }
        });

        timeSaveBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const buildingId = parseInt(card.dataset.buildingId);
            const startTime = startTimeInput.value;
            const endTime = endTimeInput.value;

            if (!startTime || !endTime) {
                this.showNotification('Both start and end times are required.', true);
                return;
            }

            try {
                await this.apiRequest(`buildings/${buildingId}/time`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        building_id: buildingId,
                        start_time: startTime,
                        end_time: endTime
                    })
                });
                this.showNotification('Building schedule updated successfully');
            } catch (error) {
                this.showNotification('Failed to update building schedule', true);
            }
        });

        let searchDebounceTimer;
        itemSearch.addEventListener('input', () => {
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                this.loadItemsForBuilding(card, true, itemSearch.value.trim());
            }, 400);
        });

        disarmBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.showIgnoreSelectionModal(card.dataset.buildingId, 'disarm');
        });
    },

    // 7. Item/Device Logic
    
    async loadItemsForBuilding(card, reset = false, search = '') {
        const buildingId = card.dataset.buildingId;
        const itemsList = card.querySelector('.items-list');
        const loader = card.querySelector('.building-loader');

        if (reset) itemsList.innerHTML = '';
        loader.style.display = 'block';

        try {
            const items = await this.apiRequest(`devices?building=${buildingId}&limit=${this.BUILD_PAGE_SIZE}&search=${encodeURIComponent(search)}`);
            if (items.length === 0 && reset) {
                itemsList.innerHTML = '<li class="muted">No proevents found.</li>';
            } else {
                items.forEach(item => itemsList.appendChild(this.createItem(item)));
            }
        } finally {
            loader.style.display = 'none';
            this.updateBuildingStatus(card);
        }
    },

    createItem(item) {
        const li = document.createElement('li');
        const state = (item.state || 'unknown').toLowerCase();
        li.className = 'device-item';
        li.dataset.itemId = item.id;
        li.dataset.state = state;

        const stateClass = state === 'armed' ? 'status-all-armed' : 'state-unknown';

        li.innerHTML = `
            <span class="device-state-indicator ${stateClass}" style="background-color: ${state === 'armed' ? '#22c55e' : '#f59e0b'};"></span>
            <div class="device-name">${this.escapeHtml(item.name)} (ID: ${item.id})</div>
        `;
        return li;
    },

    updateBuildingStatus(card) {
        const items = card.querySelectorAll('.device-item');
        const statusEl = card.querySelector('.building-status');

        if (items.length === 0) {
            statusEl.textContent = 'No ProEvents';
            statusEl.className = 'building-status status-none-armed';
            return;
        }

        const armedCount = Array.from(items).filter(d => d.dataset.state === 'armed').length;

        if (armedCount === items.length) {
            statusEl.textContent = 'All Armed';
            statusEl.className = 'building-status status-all-armed';
        } else if (armedCount > 0) {
            statusEl.textContent = 'Partially Armed';
            statusEl.className = 'building-status status-partial-armed';
        } else {
            statusEl.textContent = 'All Disarmed';
            statusEl.className = 'building-status status-none-armed';
        }
    },

    // 8. Modal Logic
    
    async showIgnoreSelectionModal(buildingId, action) {
        const { 
            modalTitle, modalItemList, ignoreModal, modalSearch, 
            modalSelectAllBtn, modalConfirmBtn, modalCancelBtn, closeButton 
        } = this.elements;

        modalTitle.textContent = `Select proevents to ignore`;
        modalItemList.innerHTML = '<div class="loader">Loading...</div>';
        ignoreModal.style.display = 'block';
        
        modalSearch.value = '';
        modalSelectAllBtn.textContent = 'Select All';

        const items = await this.apiRequest(`devices?building=${buildingId}&limit=1000`);
        modalItemList.innerHTML = '';
        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'device-item';
            div.dataset.itemId = item.id;
            
            div.innerHTML = `
                <div class="device-name">${this.escapeHtml(item.name)}</div>
                <label class="ignore-alarm-label">
                    <input type="checkbox" class="ignore-item-checkbox" ${item.is_ignored ? 'checked' : ''} />
                    Ignore Alert
                </label>
            `;
            modalItemList.appendChild(div);
        });
        
        modalSearch.oninput = () => {
            const query = modalSearch.value.toLowerCase();
            const modalItems = modalItemList.querySelectorAll('.device-item');
            modalItems.forEach(item => {
                const name = item.querySelector('.device-name').textContent.toLowerCase();
                item.style.display = name.includes(query) ? 'flex' : 'none';
            });
            modalSelectAllBtn.textContent = 'Select All';
        };
        
        modalSelectAllBtn.onclick = () => {
            const isSelectAll = modalSelectAllBtn.textContent === 'Select All';
            const modalItems = modalItemList.querySelectorAll('.device-item');
            modalItems.forEach(item => {
                if (item.style.display !== 'none') {
                    const checkbox = item.querySelector('.ignore-item-checkbox');
                    if (checkbox) checkbox.checked = isSelectAll;
                }
            });
            modalSelectAllBtn.textContent = isSelectAll ? 'Deselect All' : 'Select All';
        };

        // --- **** THIS IS THE MODIFIED FUNCTION **** ---
        modalConfirmBtn.onclick = async () => {
            const selectedItems = [];
            const itemElements = modalItemList.querySelectorAll('.device-item');
            
            itemElements.forEach(itemEl => {
                const checkbox = itemEl.querySelector('.ignore-item-checkbox');
                const itemId = parseInt(itemEl.dataset.itemId, 10);
                
                selectedItems.push({
                    item_id: itemId,
                    building_frk: parseInt(buildingId),
                    device_prk: itemId, 
                    ignore: checkbox.checked
                });
            });

            try {
                // 1. Save the new ignore settings
                await this.apiRequest('proevents/ignore/bulk', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items: selectedItems })
                });
                this.showNotification('Ignore settings saved. Applying changes...');
                
                // 2. Call the new endpoint to re-evaluate the building state
                // This runs the backend logic using the new rules.
                await this.apiRequest(`buildings/${buildingId}/reevaluate`, {
                    method: 'POST'
                });
                this.showNotification('Changes applied successfully.');

                // 3. Refresh the building view
                const card = document.querySelector(`.building-card[data-building-id='${buildingId}']`);
                if (card) {
                    const itemSearch = card.querySelector('.item-search');
                    this.loadItemsForBuilding(card, true, itemSearch.value.trim());
                }
            } catch (error) {
                this.showNotification('Failed to apply changes.', true);
            } finally {
                closeModal();
            }
        };
        
        const closeModal = () => {
            ignoreModal.style.display = 'none';
            modalSearch.oninput = null;
            modalSelectAllBtn.onclick = null;
            modalConfirmBtn.onclick = null;
        };

        modalCancelBtn.onclick = closeModal;
        closeButton.onclick = closeModal;
    }
};