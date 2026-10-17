/**
 * main.js — Frontend entry point.
 *
 * Loaded last: binds the header/mic controls to the voice session. The
 * inline onclick attributes of the old single-file page were replaced by
 * the listeners installed here.
 */

micBtn.addEventListener('click', toggleSession);
muteBtn.addEventListener('click', toggleMute);

console.log('[WorkerSaathi] voice client ready — click the microphone to start.');
