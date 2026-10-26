import { eveChannel } from "eve/channels/eve";

// Keep Eve's internal callback routes for durable sessions, but deny its
// public session API. Discovery enters only through the authenticated bridge.
export default eveChannel({ auth: () => null });
