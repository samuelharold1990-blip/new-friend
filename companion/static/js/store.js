// Tiny shared state + event emitter.

const listeners = {};

export const store = {
  settings: null,
  health: null,
  messages: [],
  oldestId: null,
  firstProactiveId: null, // where to draw the "new messages" divider
  sending: false,

  on(event, fn) {
    (listeners[event] ||= []).push(fn);
  },
  emit(event, payload) {
    (listeners[event] || []).forEach((fn) => fn(payload));
  },
};
