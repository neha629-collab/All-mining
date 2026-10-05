const fs = require('fs');
const path = require('path');

const LOG_LEVELS = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 };
const CURRENT_LEVEL = LOG_LEVELS[process.env.LOG_LEVEL?.toUpperCase()] || LOG_LEVELS.INFO;

function formatMsg(level, scope, msg) {
  const ts = new Date().toISOString().replace('T', ' ').substring(0, 19);
  return `[${ts}] [${level}] [${scope}] ${msg}`;
}

function createLogger(scope = 'APP') {
  return {
    debug: (msg) => {
      if (CURRENT_LEVEL <= LOG_LEVELS.DEBUG) console.debug(formatMsg('DEBUG', scope, msg));
    },
    info: (msg) => {
      if (CURRENT_LEVEL <= LOG_LEVELS.INFO) console.log(formatMsg('INFO', scope, msg));
    },
    warn: (msg) => {
      if (CURRENT_LEVEL <= LOG_LEVELS.WARNING) console.warn(formatMsg('WARN', scope, msg));
    },
    error: (msg, err = '') => {
      if (CURRENT_LEVEL <= LOG_LEVELS.ERROR) console.error(formatMsg('ERROR', scope, msg), err);
    }
  };
}

module.exports = {
  createLogger,
  log: createLogger('CORE'),
  botLog: createLogger('BOT'),
  apiLog: createLogger('API'),
  schedLog: createLogger('SCHED')
};
