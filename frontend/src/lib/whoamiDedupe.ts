/**
 * Whoami Deduplication Utility
 * Prevents duplicate whoami requests within a short time window
 */

let skipOnce = false;

export const whoamiDedupe = {
    shouldDedupe() {
        if (skipOnce) {
            skipOnce = false;
            return false;
        }
        return true;
    },
    disableOnce() {
        skipOnce = true;
    },
};
