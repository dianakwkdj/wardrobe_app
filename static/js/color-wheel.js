(function () {
    function initWheel(fieldset) {
        const input = fieldset.querySelector('[data-wheel-input]');
        const current = fieldset.querySelector('[data-wheel-current]');
        const wheel = fieldset.querySelector('[data-wheel]');
        const choices = Array.from(fieldset.querySelectorAll('.wheel-segment, .wheel-center-choice'));
        if (!input || !choices.length) return;

        function labelFor(value) {
            const match = choices.find(choice => (choice.dataset.color || '') === (value || ''));
            if (match) return match.dataset.label || value || '';
            return wheel?.dataset.emptyLabel || 'Не указан';
        }

        function setValue(value) {
            const normalized = value || '';
            input.value = normalized;
            choices.forEach(choice => {
                choice.classList.toggle('is-selected', (choice.dataset.color || '') === normalized);
            });
            if (current) current.textContent = labelFor(normalized);
        }

        choices.forEach(choice => {
            choice.addEventListener('click', function () {
                setValue(this.dataset.color || '');
            });
        });

        setValue(input.value || '');
    }

    document.querySelectorAll('.wheel-fieldset').forEach(initWheel);
})();
