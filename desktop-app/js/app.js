/**
 * Simple Live2D Loader for Lapwing
 * Loads and displays Hiyori model
 */

// Wait for Cubism SDK to load
document.addEventListener('DOMContentLoaded', function() {
    initLive2D();
});

function initLive2D() {
    const canvas = document.getElementById('live2d-canvas');

    // Check if Live2D is available
    if (typeof Live2DCubismCore === 'undefined') {
        console.error('Live2D Cubism Core not loaded');
        showFallbackMessage();
        return;
    }

    console.log('[Live2D] Initializing...');

    // Initialize WebGL context
    const gl = canvas.getContext('webgl2', {
        alpha: true,
        premultipliedAlpha: true,
        preserveDrawingBuffer: true
    });

    if (!gl) {
        console.error('WebGL2 not supported');
        showFallbackMessage();
        return;
    }

    // Set canvas size
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Load model
    loadHiyoriModel(gl, canvas);
}

function resizeCanvas() {
    const canvas = document.getElementById('live2d-canvas');
    const container = document.getElementById('canvas-container');

    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
}

async function loadHiyoriModel(gl, canvas) {
    try {
        // Model path
        const modelPath = 'models/hiyori/Hiyori.model3.json';

        console.log('[Live2D] Loading model:', modelPath);

        // Fetch model JSON
        const response = await fetch(modelPath);
        const modelJson = await response.json();

        console.log('[Live2D] Model loaded:', modelJson);

        // Store reference
        window.currentModel = {
            json: modelJson,
            gl: gl,
            canvas: canvas
        };

        // Start render loop
        startRenderLoop();

        // Show success in chat bubble
        showBubble('Hiyori is ready!');

    } catch (e) {
        console.error('[Live2D] Failed to load model:', e);
        showFallbackMessage();
    }
}

function startRenderLoop() {
    function render() {
        // Placeholder render - just clear the canvas with transparent
        const canvas = document.getElementById('live2d-canvas');
        const gl = canvas.getContext('webgl2');

        if (gl) {
            gl.clearColor(0, 0, 0, 0);
            gl.clear(gl.COLOR_BUFFER_BIT);
        }

        requestAnimationFrame(render);
    }

    requestAnimationFrame(render);
}

function showFallbackMessage() {
    const bubble = document.getElementById('chat-bubble');
    bubble.textContent = 'Live2D model could not be loaded, but I am still here!';
    bubble.classList.add('show');

    setTimeout(() => {
        bubble.classList.remove('show');
    }, 5000);
}

function showBubble(text) {
    const bubble = document.getElementById('chat-bubble');
    bubble.textContent = text;
    bubble.classList.add('show');

    setTimeout(() => {
        bubble.classList.remove('show');
    }, 5000);
}

// Expose functions for Python bridge
window.Live2DApp = {
    showBubble: showBubble,
    setExpression: function(name) {
        console.log('[Live2D] Expression:', name);
    },
    startMotion: function(name) {
        console.log('[Live2D] Motion:', name);
    },
    startSpeaking: function() {
        console.log('[Live2D] Start speaking');
    },
    stopSpeaking: function() {
        console.log('[Live2D] Stop speaking');
    }
};
