import streamlit as st
import numpy as np
import pandas as pd
import hashlib
import hmac
import matplotlib.pyplot as plt
from scipy.linalg import toeplitz

# -----------------------------------------------------------------------------
# SET PAGE CONFIG (light theme)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="BB84 QKD – Full Protocol Simulator",
    page_icon="⚛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# CRYPTO HELPERS
# -----------------------------------------------------------------------------
def hmac_sha256(key: bytes, message: str) -> str:
    """Return HMAC-SHA256 hex digest."""
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()

# -----------------------------------------------------------------------------
# QUANTUM LAYER
# -----------------------------------------------------------------------------
class QuantumChannel:
    """
    Models a depolarising channel with loss and dark counts.
    """
    def __init__(self, loss_prob: float = 0.0, dark_count_prob: float = 0.0,
                 depolar_prob: float = 0.0, rotation_angle: float = 0.0):
        self.loss_prob = loss_prob
        self.dark_count_prob = dark_count_prob
        self.depolar_prob = depolar_prob
        self.rotation_angle = rotation_angle

    def transmit(self, states: np.ndarray) -> tuple:
        """
        Apply channel effects to each photon.
        Returns (received_states, detected_flags) where detected_flags is True
        if Bob receives a photon (not lost) and not a dark count.
        """
        received = []
        detected = []
        for state in states:
            # Loss: photon may not arrive
            if np.random.random() < self.loss_prob:
                received.append(state)  # no photon, but we keep state for indexing
                detected.append(False)
                continue

            # Dark count: detector fires even without photon (random bit)
            if np.random.random() < self.dark_count_prob:
                # produce random state (corresponding to random bit in Z basis)
                random_bit = np.random.randint(2)
                random_state = 0.0 if random_bit == 0 else 90.0
                received.append(random_state)
                detected.append(True)
                continue

            # Polarisation rotation (fixed angle)
            rotated = state + self.rotation_angle

            # Depolarisation: with prob p, replace with completely mixed state
            if np.random.random() < self.depolar_prob:
                # mixed state -> random measurement outcome in any basis
                # we store a special value that measurement will treat as random
                received.append(-1)  # flag for mixed state
                detected.append(True)
            else:
                received.append(rotated % 180)
                detected.append(True)

        return np.array(received), np.array(detected)

# -----------------------------------------------------------------------------
# ALICE
# -----------------------------------------------------------------------------
class Alice:
    def __init__(self, size: int):
        self.size = size
        self.bits = np.random.randint(2, size=size)
        self.bases = np.random.choice(['Z', 'X'], size=size)

    def encode(self) -> np.ndarray:
        """Encode bits in polarisation states (degrees)."""
        states = []
        for bit, basis in zip(self.bits, self.bases):
            if basis == 'Z':
                states.append(0.0 if bit == 0 else 90.0)
            else:
                states.append(45.0 if bit == 0 else 135.0)
        return np.array(states)

# -----------------------------------------------------------------------------
# BOB
# -----------------------------------------------------------------------------
class Bob:
    def __init__(self, size: int):
        self.size = size
        self.bases = np.random.choice(['Z', 'X'], size=size)
        self.results = []
        self.detected = []

    def measure(self, states: np.ndarray, detected_flags: np.ndarray) -> np.ndarray:
        """Measure received photons considering detection flags."""
        self.results = []
        self.detected = detected_flags
        for state, flag in zip(states, detected_flags):
            if not flag:
                # photon lost, mark result as -1 (undefined)
                self.results.append(-1)
                continue
            if state == -1:  # mixed state from depolarisation
                # random outcome (depolarisation makes basis irrelevant)
                self.results.append(np.random.randint(2))
                continue

            basis = self.bases[len(self.results)]  # current index
            if basis == 'Z':
                prob_0 = np.cos(np.radians(state)) ** 2
                result = 0 if np.random.random() < prob_0 else 1
            else:  # X basis
                prob_plus = np.cos(np.radians(state - 45.0)) ** 2
                result = 0 if np.random.random() < prob_plus else 1

            self.results.append(result)

        return np.array(self.results)

# -----------------------------------------------------------------------------
# EVE (intercept‑resend with quantum memory)
# -----------------------------------------------------------------------------
class Eve:
    def __init__(self, prob_intercept: float):
        self.prob_intercept = prob_intercept
        self.bases = []
        self.results = []

    def attack(self, states: np.ndarray) -> np.ndarray:
        """Intercept‑resend attack. If not intercepted, photon passes unchanged."""
        after_eve = []
        self.bases = []
        self.results = []
        for state in states:
            if np.random.random() < self.prob_intercept:
                basis = np.random.choice(['Z', 'X'])
                self.bases.append(basis)
                if basis == 'Z':
                    prob_0 = np.cos(np.radians(state)) ** 2
                    result = 0 if np.random.random() < prob_0 else 1
                    collapsed_state = 0.0 if result == 0 else 90.0
                else:
                    prob_plus = np.cos(np.radians(state - 45.0)) ** 2
                    result = 0 if np.random.random() < prob_plus else 1
                    collapsed_state = 45.0 if result == 0 else 135.0
                self.results.append(result)
                after_eve.append(collapsed_state)
            else:
                self.bases.append('-')
                self.results.append(-1)
                after_eve.append(state)
        return np.array(after_eve)

# -----------------------------------------------------------------------------
# ERROR CORRECTION (Cascade‑like parity exchange)
# -----------------------------------------------------------------------------
def cascade_error_correction(alice_bits: list, bob_bits: list,
                             initial_block_size: int = 8, iterations: int = 4) -> tuple:
    """
    Simplified Cascade: iterative parity checks with random permutations.
    Returns corrected Bob bits, number of errors corrected, parity bits leaked.
    """
    alice = np.array(alice_bits, dtype=int)
    bob = np.array(bob_bits, dtype=int)
    n = len(alice)
    errors_corrected = 0
    leaked = 0

    bob_corrected = bob.copy()
    block_size = initial_block_size

    for it in range(iterations):
        # Create permutation (public but authenticated in practice)
        rng = np.random.default_rng(1000 + it)  # fixed seed for demo
        perm = rng.permutation(n)

        # Process blocks
        for start in range(0, n, block_size):
            idx = perm[start:start + block_size]
            if len(idx) < 2:
                continue

            parity_a = alice[idx].sum() % 2
            parity_b = bob_corrected[idx].sum() % 2
            leaked += 1

            if parity_a != parity_b:
                # binary search
                low, high = 0, len(idx) - 1
                while low < high:
                    mid = (low + high) // 2
                    sub_idx = idx[low:mid+1]
                    sub_par_a = alice[sub_idx].sum() % 2
                    sub_par_b = bob_corrected[sub_idx].sum() % 2
                    leaked += 1
                    if sub_par_a != sub_par_b:
                        high = mid
                    else:
                        low = mid + 1
                err_pos = idx[low]
                bob_corrected[err_pos] ^= 1
                errors_corrected += 1

        # Increase block size for next iteration (Cascade doubling)
        block_size *= 2

    return bob_corrected.tolist(), errors_corrected, leaked

# -----------------------------------------------------------------------------
# PRIVACY AMPLIFICATION (Toeplitz hashing)
# -----------------------------------------------------------------------------
def toeplitz_privacy_amplification(bits: list, final_len: int, auth_key: bytes) -> list:
    """
    Use a random Toeplitz matrix for privacy amplification.
    The matrix is public (authenticated) but generated from a shared secret.
    """
    n = len(bits)
    if final_len >= n:
        raise ValueError("final_len must be smaller than input length")

    # Generate first row and first column of Toeplitz matrix
    # In practice, Alice and Bob agree on a random seed publicly (authenticated)
    rng = np.random.default_rng(int.from_bytes(auth_key[:4], 'big') % (2**32))
    first_row = rng.integers(0, 2, n, dtype=np.uint8)
    first_col = rng.integers(0, 2, final_len, dtype=np.uint8)
    first_col[0] = first_row[0]  # ensure consistency

    # Construct Toeplitz matrix (final_len x n)
    # scipy.linalg.toeplitz(c, r) creates matrix with first column c, first row r
    matrix = toeplitz(first_col, first_row).astype(np.uint8) % 2

    bits_array = np.array(bits, dtype=np.uint8).reshape(-1, 1)
    hashed = (matrix @ bits_array) % 2
    return hashed.flatten().tolist()

# -----------------------------------------------------------------------------
# MAIN SIMULATION
# -----------------------------------------------------------------------------
class BB84FullSimulation:
    def __init__(self, num_qubits, eve_prob=0.0, channel_params=None,
                 sacrifice_pct=0.20, qber_threshold=0.11, seed=42,
                 enable_ec=True, enable_pa=True, enable_auth=True):
        self.num_qubits = num_qubits
        self.eve_prob = eve_prob
        self.channel_params = channel_params or {}
        self.sacrifice_pct = sacrifice_pct
        self.qber_threshold = qber_threshold
        self.seed = seed
        self.enable_ec = enable_ec
        self.enable_pa = enable_pa
        self.enable_auth = enable_auth

        # Authentication key (simulated pre‑shared secret)
        self.auth_key = hashlib.sha256(str(seed).encode()).digest() if enable_auth else b""

        # Set seeds
        np.random.seed(seed)

        # Create parties
        self.alice = Alice(num_qubits)
        self.eve = Eve(eve_prob)
        self.bob = Bob(num_qubits)

        # Create quantum channel
        self.channel = QuantumChannel(
            loss_prob=channel_params.get('loss', 0.0),
            dark_count_prob=channel_params.get('dark_count', 0.0),
            depolar_prob=channel_params.get('depolar', 0.0),
            rotation_angle=channel_params.get('rotation', 0.0)
        )

    def run(self):
        # 1. Alice encodes
        sent_states = self.alice.encode()

        # 2. Eve attacks (intercept‑resend)
        after_eve = self.eve.attack(sent_states)

        # 3. Quantum channel
        channel_states, detected = self.channel.transmit(after_eve)

        # 4. Bob measures
        bob_results = self.bob.measure(channel_states, detected)

        # 5. Sifting: only keep photons that Bob detected and bases match
        sifted_indices = []
        for i in range(self.num_qubits):
            if not detected[i]:
                continue  # lost photon
            if self.alice.bases[i] == self.bob.bases[i]:
                sifted_indices.append(i)

        sifted_len = len(sifted_indices)
        if sifted_len == 0:
            return self._abort("No photons survived and matched bases.")

        # 6. QBER estimation
        num_sacrifice = max(1, int(sifted_len * self.sacrifice_pct))
        sacrifice_indices = np.random.choice(sifted_indices, size=num_sacrifice, replace=False)
        # Bob's results for sacrifice bits (all detected and bases matched)
        sacrifice_bits_alice = [self.alice.bits[i] for i in sacrifice_indices]
        sacrifice_bits_bob = [self.bob.results[i] for i in sacrifice_indices]
        errors = sum(1 for a,b in zip(sacrifice_bits_alice, sacrifice_bits_bob) if a != b)
        qber = errors / num_sacrifice

        # 7. Abort if QBER too high
        if qber >= self.qber_threshold:
            return self._abort(f"QBER {qber:.2%} ≥ threshold {self.qber_threshold:.2%}")

        # 8. Remaining sifted bits
        remaining_indices = [i for i in sifted_indices if i not in sacrifice_indices]
        alice_raw = [self.alice.bits[i] for i in remaining_indices]
        bob_raw = [self.bob.results[i] for i in remaining_indices]

        # 9. Error correction (if enabled)
        if self.enable_ec and len(alice_raw) > 0:
            bob_corrected, ec_errors, parity_leaked = cascade_error_correction(
                alice_raw, bob_raw, initial_block_size=8, iterations=4
            )
        else:
            bob_corrected = bob_raw
            ec_errors = 0
            parity_leaked = 0

        # 10. Privacy amplification (if enabled)
        if self.enable_pa and len(alice_raw) > 0:
            # Estimate final key length from QBER (simple heuristic)
            # Actual formula: n * (1 - h2(QBER)) minus security margin
            # We'll use a simple linear reduction.
            final_len = max(1, int(len(alice_raw) * (1 - 1.5 * qber) * 0.8))
            alice_final = toeplitz_privacy_amplification(alice_raw, final_len, self.auth_key)
            bob_final = toeplitz_privacy_amplification(bob_corrected, final_len, self.auth_key)
        else:
            final_len = len(alice_raw)
            alice_final = alice_raw
            bob_final = bob_corrected

        # 11. Key match check
        keys_match = (alice_final == bob_final)

        # 12. Hash for display
        alice_key_str = "".join(map(str, alice_final))
        bob_key_str = "".join(map(str, bob_final))
        alice_hash = hashlib.sha256(alice_key_str.encode()).hexdigest()[:16] if alice_key_str else "N/A"
        bob_hash = hashlib.sha256(bob_key_str.encode()).hexdigest()[:16] if bob_key_str else "N/A"

        # 13. Authentication log
        auth_log = []
        if self.enable_auth:
            # Authenticate basis announcements
            alice_bases_msg = "".join(self.alice.bases)
            bob_bases_msg = "".join(self.bob.bases)
            tag1 = hmac_sha256(self.auth_key, "Alice_bases:" + alice_bases_msg)
            tag2 = hmac_sha256(self.auth_key, "Bob_bases:" + bob_bases_msg)
            auth_log.append(("Alice basis announcement", tag1[:16]))
            auth_log.append(("Bob basis announcement", tag2[:16]))
            if self.enable_ec:
                tag3 = hmac_sha256(self.auth_key, f"Parity info (leaked {parity_leaked} bits)")
                auth_log.append(("Error correction parity exchange", tag3[:16]))
            if self.enable_pa:
                tag4 = hmac_sha256(self.auth_key, f"PA matrix (final length {final_len})")
                auth_log.append(("Privacy amplification matrix", tag4[:16]))

        return {
            "aborted": False,
            "qber": qber,
            "sifted_len": sifted_len,
            "sacrifice_len": num_sacrifice,
            "remaining_raw_len": len(alice_raw),
            "ec_errors_corrected": ec_errors,
            "parity_leaked": parity_leaked,
            "final_len": final_len,
            "alice_key": alice_key_str,
            "bob_key": bob_key_str,
            "alice_hash": alice_hash,
            "bob_hash": bob_hash,
            "keys_match": keys_match,
            "auth_log": auth_log,
            "alice_raw": "".join(map(str, alice_raw)),
            "bob_raw": "".join(map(str, bob_raw)),
            "bob_corrected": "".join(map(str, bob_corrected)),
            "alice_final": alice_key_str,
            "bob_final": bob_key_str,
            "lost_photons": int(np.sum(~detected)),
            "dark_counts": int(np.sum([1 for i in range(self.num_qubits) if not detected[i] and channel_states[i] != after_eve[i]])),
        }

    def _abort(self, reason):
        return {
            "aborted": True,
            "reason": reason,
            "qber": 0.0,
            "sifted_len": 0,
            "sacrifice_len": 0,
            "remaining_raw_len": 0,
            "ec_errors_corrected": 0,
            "parity_leaked": 0,
            "final_len": 0,
            "alice_key": "",
            "bob_key": "",
            "alice_hash": "DISCARDED",
            "bob_hash": "DISCARDED",
            "keys_match": False,
            "auth_log": [],
            "alice_raw": "",
            "bob_raw": "",
            "bob_corrected": "",
            "alice_final": "",
            "bob_final": "",
            "lost_photons": 0,
            "dark_counts": 0,
        }

# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.title("⚛️ BB84 QKD – Full Protocol Simulator")
st.markdown("""
This simulator implements the complete BB84 quantum key distribution protocol with  
realistic channel impairments, error correction, privacy amplification, and authentication.
""")

# Sidebar controls
st.sidebar.header("Parameters")
seed = st.sidebar.number_input("Random Seed", 0, 10000, 42)
total_qubits = st.sidebar.slider("Number of Qubits", 20, 300, 100, step=10)

eve_active = st.sidebar.checkbox("Enable Eve", value=True)
eve_prob = st.sidebar.slider("Eve Interception Probability", 0.0, 1.0, 1.0, 0.1) if eve_active else 0.0

st.sidebar.subheader("Channel Parameters")
loss_prob = st.sidebar.slider("Photon Loss Probability", 0.0, 0.5, 0.0, 0.01)
dark_count_prob = st.sidebar.slider("Dark Count Probability", 0.0, 0.1, 0.0, 0.001)
depolar_prob = st.sidebar.slider("Depolarisation Probability", 0.0, 0.3, 0.0, 0.01)
rotation_angle = st.sidebar.slider("Polarisation Rotation (degrees)", 0.0, 45.0, 0.0, 1.0)

st.sidebar.subheader("Protocol Parameters")
sacrifice_ratio = st.sidebar.slider("Sacrifice Ratio", 0.1, 0.4, 0.2, 0.05)
qber_threshold = st.sidebar.slider("QBER Abort Threshold", 0.05, 0.25, 0.11, 0.01)

st.sidebar.subheader("Advanced")
enable_ec = st.sidebar.checkbox("Error Correction", value=True)
enable_pa = st.sidebar.checkbox("Privacy Amplification", value=True)
enable_auth = st.sidebar.checkbox("Authenticated Classical Channel", value=True)

# Create and run simulation
sim = BB84FullSimulation(
    num_qubits=total_qubits,
    eve_prob=eve_prob,
    channel_params={
        'loss': loss_prob,
        'dark_count': dark_count_prob,
        'depolar': depolar_prob,
        'rotation': rotation_angle
    },
    sacrifice_pct=sacrifice_ratio,
    qber_threshold=qber_threshold,
    seed=seed,
    enable_ec=enable_ec,
    enable_pa=enable_pa,
    enable_auth=enable_auth
)
results = sim.run()

# Metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Sifted Bits", results['sifted_len'])
col2.metric("QBER", f"{results['qber']:.2%}")
col3.metric("Final Key Length", results['final_len'])
col4.metric("Status", "✅ Accepted" if not results['aborted'] else "❌ Aborted")

if results['aborted']:
    st.error(f"Aborted: {results['reason']}")
else:
    st.success(f"Key established with length {results['final_len']} bits.")

# Tabs
tabs = st.tabs(["📊 Overview", "🔍 Detailed Log", "🔐 Key Pipeline", "🔬 Security"])

with tabs[0]:
    st.subheader("Protocol Performance")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    fig.patch.set_facecolor('white')

    # Pie chart
    labels = ['Sacrifice', 'Final Key', 'Mismatch/Lost']
    sizes = [results['sacrifice_len'], results['final_len'],
             total_qubits - results['sifted_len'] + (results['remaining_raw_len'] - results['final_len'])]
    colors = ['#FFC107', '#00B4D8', '#D3D3D3']
    axes[0].pie(sizes, labels=None, autopct='%1.1f%%', colors=colors)
    axes[0].legend(labels, loc='lower center', bbox_to_anchor=(0.5, -0.2), ncol=3)
    axes[0].set_title("Bit Utilisation")

    # Bar chart QBER
    axes[1].bar(['QBER', 'Threshold'], [results['qber']*100, qber_threshold*100],
                color=['#FF4B4B' if results['qber'] >= qber_threshold else '#00B4D8', '#D3D3D3'])
    axes[1].set_title("QBER vs Threshold (%)")

    # Loss and dark counts
    axes[2].bar(['Lost', 'Dark Counts'], [results['lost_photons'], results['dark_counts']],
                color=['#FF9800', '#9E9E9E'])
    axes[2].set_title("Channel Loss & Dark Counts")

    st.pyplot(fig)
    plt.close(fig)

    st.write(f"Errors corrected: {results['ec_errors_corrected']}")
    st.write(f"Parity bits leaked: {results['parity_leaked']}")

with tabs[1]:
    st.subheader("Qubit‑by‑Qubit Log")
    # Build dataframe
    rows = []
    for i in range(total_qubits):
        rows.append({
            "Index": i,
            "Alice Bit": sim.alice.bits[i],
            "Alice Basis": sim.alice.bases[i],
            "Eve Basis": sim.eve.bases[i] if eve_active else "-",
            "Eve Result": sim.eve.results[i] if eve_active else "-",
            "Bob Basis": sim.bob.bases[i],
            "Bob Result": sim.bob.results[i] if sim.bob.detected[i] else "Lost",
            "Detected": sim.bob.detected[i],
            "Bases Match": "YES" if sim.alice.bases[i] == sim.bob.bases[i] else "NO"
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, height=400)

with tabs[2]:
    st.subheader("Key Distillation Steps")
    if results['aborted']:
        st.warning("No key generated.")
    else:
        st.markdown("**Raw Sifted Key (Alice)**")
        st.code(results['alice_raw'])
        st.markdown("**Raw Sifted Key (Bob)**")
        st.code(results['bob_raw'])
        if enable_ec:
            st.markdown("**After Error Correction (Bob)**")
            st.code(results['bob_corrected'])
        if enable_pa:
            st.markdown("**Final Key (Alice)**")
            st.code(results['alice_final'])
            st.markdown("**Final Key (Bob)**")
            st.code(results['bob_final'])
        st.markdown("**Hash Check**")
        st.code(f"Alice: {results['alice_hash']}    Bob: {results['bob_hash']}")
        if results['keys_match']:
            st.success("Keys match.")
        else:
            st.error("Keys do not match!")

with tabs[3]:
    st.subheader("Security Log")
    if enable_auth:
        st.write("Authenticated messages (HMAC‑SHA256):")
        for msg, tag in results['auth_log']:
            st.write(f"- {msg}: `{tag}...`")
    else:
        st.info("Authentication disabled.")
    st.markdown("---")
    st.write("**Security Parameters:**")
    st.write(f"- QBER estimated: {results['qber']:.2%}")
    st.write(f"- Sacrifice bits: {results['sacrifice_len']}")
    st.write(f"- Parity bits leaked: {results['parity_leaked']}")
    st.write(f"- Final key length: {results['final_len']}")

st.markdown("---")
st.markdown("This simulator provides a realistic implementation of BB84 with all essential post‑processing steps.")
