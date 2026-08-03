const os = require("node:os");

const readNetworkInterfaces = os.networkInterfaces;
os.networkInterfaces = function networkInterfacesWithFallback() {
  try {
    return readNetworkInterfaces.call(os);
  } catch {
    return {};
  }
};
