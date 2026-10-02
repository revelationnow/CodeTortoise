import { plainHttpOnNetwork } from "../lib/insecure";

/** Amber strip on every page while the connection is plain HTTP over the network (spec §14.2). */
export default function InsecureBanner() {
  if (!plainHttpOnNetwork(window.location.protocol, window.location.hostname)) return null;
  return <div className="insecure" role="alert">Not encrypted — this connection to CodeTortoise is plain HTTP over the network.</div>;
}
