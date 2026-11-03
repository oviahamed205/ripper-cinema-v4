import { IpcServer } from './ipc_server';
import { TelemetryStreamer } from './telemetry_stream';

async function main() {
  const ipc = new IpcServer();
  const streamer = new TelemetryStreamer(8799);

  ipc.onTelemetry((pkt) => {
    console.log(`[TELEMETRY][${pkt.level}] ${pkt.source}: ${pkt.message}`);
    streamer.publish(pkt);
  });

  await ipc.start();
  await streamer.start();

  console.log('Autonomous Healer Daemon is operational.');

  const shutdown = async () => {
    console.log('Shutting down healer daemon...');
    await ipc.stop();
    await streamer.stop();
    process.exit(0);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

if (require.main === module) {
  main().catch(console.error);
}
