/**
 * Mr. Yeti Avatar Controller
 * Manages animations, speech bubbles, and states
 */

class MrYeti {
    constructor(containerId = 'mr-yeti-container') {
        this.container = document.getElementById(containerId) || this.createContainer();
        this.speechBubble = this.container.querySelector('.yeti-speech-bubble');
        this.avatar = this.container.querySelector('.mr-yeti-avatar');
        this.isTalking = false;
        this.messageQueue = [];

        this.init();
    }

    createContainer() {
        const div = document.createElement('div');
        div.id = 'mr-yeti-container';
        div.className = 'mr-yeti-container';
        div.innerHTML = `
            <div class="yeti-speech-bubble" id="yeti-speech">
                Hello! I'm Mr. Yeti! 🏔️
            </div>
            <div class="mr-yeti-avatar" id="mr-yeti-avatar">
                <div class="yeti-head">
                    <div class="yeti-eye left"></div>
                    <div class="yeti-eye right"></div>
                    <div class="yeti-mouth" id="yeti-mouth"></div>
                </div>
                <div class="yeti-body"></div>
                <div class="yeti-arm left"></div>
                <div class="yeti-arm right"></div>
            </div>
        `;
        document.body.appendChild(div);
        return div;
    }

    init() {
        this.speechBubble.addEventListener('click', () => this.hideSpeech());
    }

    // ── Speech ───────────────────────────────────────────────────────────────

    speak(text, duration = 3000) {
        this.messageQueue.push({ text, duration });
        if (!this.isTalking) this.processQueue();
    }

    async processQueue() {
        if (this.messageQueue.length === 0) {
            this.isTalking = false;
            this.setState('idle');
            return;
        }

        this.isTalking = true;
        const { text, duration } = this.messageQueue.shift();

        this.setState('talking');
        this.showSpeech(text);

        // Auto-size display time: ~200 wpm reading speed, capped at 8 s
        const words = text.split(' ').length;
        const readTime = Math.max(2000, (words / 200) * 60000);
        const displayTime = Math.min(duration || readTime, 8000);

        await this.sleep(displayTime);
        this.hideSpeech();
        await this.sleep(500);
        this.processQueue();
    }

    showSpeech(text) {
        this.speechBubble.textContent = text;
        this.speechBubble.classList.add('visible');
    }

    hideSpeech() {
        this.speechBubble.classList.remove('visible');
    }

    // ── State ────────────────────────────────────────────────────────────────

    setState(state) {
        this.avatar.className = 'mr-yeti-avatar';
        const mouth = document.getElementById('yeti-mouth');

        switch (state) {
            case 'talking':
                this.avatar.classList.add('talking');
                mouth && mouth.classList.add('talking');
                break;
            case 'listening':
                this.avatar.classList.add('listening');
                break;
            case 'celebrating':
                this.avatar.classList.add('celebrating');
                this.spawnConfetti();
                break;
            case 'waving':
                this.avatar.classList.add('waving');
                break;
            case 'sad':
                mouth && mouth.classList.add('sad');
                break;
            case 'happy':
                mouth && mouth.classList.add('smile');
                break;
            // 'idle' — default, no extra class needed
        }
    }

    // ── Emotion shortcuts ────────────────────────────────────────────────────

    celebrate(message = 'Amazing work! 🎉') {
        this.setState('celebrating');
        this.speak(message, 4000);
        setTimeout(() => this.setState('idle'), 4000);
    }

    encourage(message) {
        this.setState('happy');
        this.speak(message, 3000);
    }

    correct(message) {
        this.setState('talking');
        this.speak('Let\'s fix this! ' + message, 4000);
    }

    listen() {
        this.setState('listening');
    }

    wave() {
        this.setState('waving');
        setTimeout(() => this.setState('idle'), 2000);
    }

    // ── Visual effects ───────────────────────────────────────────────────────

    spawnConfetti() {
        const colors = ['#FFD700', '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4'];
        for (let i = 0; i < 20; i++) {
            setTimeout(() => {
                const el = document.createElement('div');
                el.className = 'confetti';
                el.style.left = Math.random() * 150 + 'px';
                el.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
                el.style.animationDelay = Math.random() * 0.5 + 's';
                this.avatar.appendChild(el);
                setTimeout(() => el.remove(), 3000);
            }, i * 50);
        }
    }

    // ── Utility ──────────────────────────────────────────────────────────────

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

window.MrYeti = MrYeti;
