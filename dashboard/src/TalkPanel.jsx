import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Room, RoomEvent, Track } from 'livekit-client';
import { Mic, MicOff, Phone, PhoneOff, Loader2 } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function TalkPanel() {
  const [status, setStatus] = useState('idle'); // idle | connecting | live | error
  const [error, setError] = useState('');
  const [micEnabled, setMicEnabled] = useState(true);
  const [agentPresent, setAgentPresent] = useState(false);
  const [roomName, setRoomName] = useState('');
  const [log, setLog] = useState([]);

  const roomRef = useRef(null);
  const audioElsRef = useRef(new Map());

  const pushLog = useCallback((line) => {
    const stamp = new Date().toLocaleTimeString('en-IN', { hour12: false });
    setLog((prev) => [`[${stamp}] ${line}`, ...prev].slice(0, 40));
  }, []);

  const detachAudio = useCallback(() => {
    audioElsRef.current.forEach((el) => {
      el.pause();
      el.srcObject = null;
      el.remove();
    });
    audioElsRef.current.clear();
  }, []);

  const attachTrack = useCallback((track, participant) => {
    if (track.kind !== Track.Kind.Audio) return;
    const el = track.attach();
    el.autoplay = true;
    el.playsInline = true;
    el.style.display = 'none';
    document.body.appendChild(el);
    audioElsRef.current.set(track.sid, el);
    pushLog(`Hearing ${participant.identity}`);
  }, [pushLog]);

  const endCall = useCallback(async () => {
    const room = roomRef.current;
    roomRef.current = null;
    if (room) {
      room.removeAllListeners();
      await room.disconnect();
    }
    detachAudio();
    setAgentPresent(false);
    setRoomName('');
    setStatus('idle');
    pushLog('Call ended');
  }, [detachAudio, pushLog]);

  const startCall = useCallback(async () => {
    setError('');
    setStatus('connecting');
    setLog([]);
    pushLog('Requesting room token...');

    try {
      const res = await fetch(`${API_BASE_URL}/api/livekit/token`, { method: 'POST' });
      const raw = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg =
          raw?.detail?.message ||
          raw?.message ||
          `Token request failed (${res.status})`;
        throw new Error(msg);
      }

      const { serverUrl, token, roomName: room, agentName } = raw;
      setRoomName(room);
      pushLog(`Joining ${room} (agent: ${agentName})`);

      const roomObj = new Room({
        adaptiveStream: true,
        dynacast: true,
      });
      roomRef.current = roomObj;

      roomObj.on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
        attachTrack(track, participant);
      });

      roomObj.on(RoomEvent.TrackUnsubscribed, (track) => {
        const el = audioElsRef.current.get(track.sid);
        if (el) {
          track.detach(el);
          el.remove();
          audioElsRef.current.delete(track.sid);
        }
      });

      roomObj.on(RoomEvent.ParticipantConnected, (participant) => {
        pushLog(`${participant.identity} joined`);
        if (participant.isAgent || participant.identity.includes('agent')) {
          setAgentPresent(true);
        }
      });

      roomObj.on(RoomEvent.ParticipantDisconnected, (participant) => {
        pushLog(`${participant.identity} left`);
        if (participant.isAgent || participant.identity.includes('agent')) {
          setAgentPresent(false);
        }
      });

      roomObj.on(RoomEvent.Disconnected, () => {
        pushLog('Disconnected from room');
        detachAudio();
        setStatus('idle');
        setAgentPresent(false);
        roomRef.current = null;
      });

      await roomObj.connect(serverUrl, token);
      await roomObj.localParticipant.setMicrophoneEnabled(true);
      setMicEnabled(true);
      setStatus('live');
      pushLog('Connected. Speak your 10-digit mobile number.');

      // Agent may already be in the room by the time we finish connecting
      roomObj.remoteParticipants.forEach((p) => {
        if (p.isAgent || p.identity.includes('agent')) {
          setAgentPresent(true);
          pushLog(`${p.identity} already in room`);
        }
        p.audioTrackPublications.forEach((pub) => {
          if (pub.track) attachTrack(pub.track, p);
        });
      });
    } catch (err) {
      console.error(err);
      setError(err.message || 'Could not start call');
      setStatus('error');
      pushLog(`Error: ${err.message || 'unknown'}`);
      await endCall();
      setStatus('error');
    }
  }, [attachTrack, detachAudio, endCall, pushLog]);

  const toggleMic = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const next = !micEnabled;
    await room.localParticipant.setMicrophoneEnabled(next);
    setMicEnabled(next);
    pushLog(next ? 'Mic on' : 'Mic muted');
  }, [micEnabled, pushLog]);

  useEffect(() => {
    return () => {
      const room = roomRef.current;
      if (room) {
        room.removeAllListeners();
        room.disconnect();
      }
      detachAudio();
    };
  }, [detachAudio]);

  return (
    <div className="talk-panel">
      <div className="talk-card">
        <div className="talk-hero">
          <div className={`talk-orb ${status === 'live' ? 'live' : ''}`}>
            <Phone className="icon-xl" />
          </div>
          <h2>Talk to the voice agent</h2>
          <p>
            Opens a LiveKit room in your browser, dispatches the agent, and uses
            your microphone. Say your number in English, Hindi, or mixed.
          </p>
        </div>

        <div className="talk-status-row">
          <span className={`pill ${status}`}>
            {status === 'idle' && 'Ready'}
            {status === 'connecting' && 'Connecting...'}
            {status === 'live' && 'On call'}
            {status === 'error' && 'Error'}
          </span>
          {status === 'live' && (
            <span className={`pill ${agentPresent ? 'agent-on' : 'agent-wait'}`}>
              {agentPresent ? 'Agent connected' : 'Waiting for agent...'}
            </span>
          )}
          {roomName && <span className="pill muted">{roomName}</span>}
        </div>

        {error && <div className="talk-error">{error}</div>}

        <div className="talk-actions">
          {status !== 'live' && status !== 'connecting' ? (
            <button type="button" className="btn btn-call" onClick={startCall}>
              <Phone className="icon" />
              Start call
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={toggleMic}
                disabled={status !== 'live'}
              >
                {micEnabled ? <Mic className="icon" /> : <MicOff className="icon" />}
                {micEnabled ? 'Mute' : 'Unmute'}
              </button>
              <button
                type="button"
                className="btn btn-end"
                onClick={endCall}
                disabled={status === 'connecting'}
              >
                {status === 'connecting' ? (
                  <Loader2 className="icon spin" />
                ) : (
                  <PhoneOff className="icon" />
                )}
                End call
              </button>
            </>
          )}
        </div>

        <div className="talk-hints">
          <p>Before you call:</p>
          <ol>
            <li>Backend running on port 8000</li>
            <li>
              Agent worker running: <code>python -m agent.main dev</code>
            </li>
            <li>Allow microphone access in the browser</li>
          </ol>
        </div>
      </div>

      <div className="talk-log panel">
        <div className="talk-log-title">Call log</div>
        {log.length === 0 ? (
          <p className="talk-log-empty">Call events will show up here.</p>
        ) : (
          <ul>
            {log.map((line, i) => (
              <li key={`${line}-${i}`}>{line}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
