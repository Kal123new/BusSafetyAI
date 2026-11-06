// Persist unresolved requests only, never access tokens or camera/GPS data.
async function database() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('safesense-pending-writes', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('writes', { keyPath: 'key' });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function transaction(mode, action) {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction('writes', mode);
      const request = action(tx.objectStore('writes'));
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}
export const rememberWrite = value => transaction('readwrite', store => store.put(value));
export const forgetWrite = key => transaction('readwrite', store => store.delete(key));
export const getPendingWrites = async owner => (await transaction('readonly', store => store.getAll())).filter(row => row.owner === owner);
