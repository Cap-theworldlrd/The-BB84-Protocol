import streamlit as st
import numpy as np
import pandas as pd
import hashlib
import hmac
import matplotlib.pyplot as plt

# -----------------------------------------------------------------------------
# STREAMLIT PAGE CONFIGURATION (Light theme)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="BB84 Quantum Key Distribution Simulator",
    page_icon="⚛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# CRYPTO HELPERS
# -----------------------------------------------------------------------------
def hmac_sha256(key: bytes, message: str) -> str:
    """Return HMAC-SHA256 hex digest used for authentication."""
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()

# -----------------------------------------------------------------------------
# CORE SIMULATION CLASSES
# -----------------------------------------------------------------------------
class Alice:
    def __init__(self, size: int):
        self.size = size
        self.bits = np.random.randint(2, size=size)
        self.bases = np.random.choice(['Z', 'X'], size=size)

    def encode(self) -> np.ndarray:
        """
        BB84 polarisation encoding:
            Z basis : bit 0 -> 0°, bit 1 -> 90°
            X basis : bit 0 -> 45°, bit 1 -> 135°
        Returns array of angles in degrees.
        """
        states = []
        for bit, basis in zip(self.bits, self.bases):
            if basis == 'Z':
                states.append(0.0 if bit == 0 else 90.0)
            else:  # X basis
                states.append(45.0 if bit == 0 else 135.0)
        return np.array(states)


class Eve:
    """Intercept‑resend eavesdropper."""
    def __init__(self, prob_intercept: float):
        self.prob_intercept = prob_intercept
        self.bases = []          # basis for each photon ('-' if not intercepted)
        self.results = []        # measurement result (0/1, or -1)

    def attack(self, states: np.ndarray) -> np.ndarray:
        """Perform intercept‑resend attack. Returns array of states after Eve."""
        intercepted_states = []
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
                else:  # X basis
                    prob_plus = np.cos(np.radians(state - 45.0)) ** 2
                    result = 0 if np.random.random() < prob_plus else 1
                    collapsed_state = 45.0 if result == 0 else 135.0

                self.results.append(result)
                intercepted_states.append(collapsed_state)
            else:
                self.bases.append('-')
                self.results.append(-1)
                intercepted_states.append(state)

        return np.array(intercepted_states)


class Bob:
    def __init__(self, size: int):
        self.size = size
        self.bases = np.random.choice(['Z', 'X'], size=size)
        self.results = []

    def measure(self, states: np.ndarray, depolarising_noise: float = 0.0) -> np.ndarray:
        """
        Measure each received photon.
        depolarising_noise: probability that the photon is replaced by a
        completely mixed state (random measurement result).
        """
        self.results = []
        for state, basis in zip(states, self.bases):
            if np.random.random() < depolarising_noise:
                self.results.append(np.random.randint(2))
                continue

            if basis == 'Z':
                prob_0 = np.cos(np.radians(state)) ** 2
                result = 0 if np.random.random() < prob_0 else 1
            else:  # X basis
                prob_plus = np.cos(np.radians(state - 45.0)) ** 2
                result = 0 if np.random.random() < prob_plus else 1

            self.results.append(result)

        return np.array(self.results)


# -----------------------------------------------------------------------------
# INFORMATION RECONCILIATION (PARITY‑BASED, SIMPLIFIED CASCADE)
# -----------------------------------------------------------------------------
def binary_error_correction(alice_bits: list, bob_bits: list, block_size: int = 8,
                            max_iterations: int = 5, auth_key: bytes = b"") -> tuple:
    """
    A simple parity‑check error correction algorithm.
    Alice and Bob divide their bit strings into blocks, compare parity,
    and if parity differs, they perform a binary search to locate an error.

    Returns corrected Bob bits, number of errors corrected, number of parity bits leaked.
    """
    alice = np.array(alice_bits, dtype=int)
    bob = np.array(bob_bits, dtype=int)
    n = len(alice)
    errors_corrected = 0
    leaked_parity_bits = 0

    bob_corrected = bob.copy()

    for iteration in range(max_iterations):
        rng = np.random.default_rng(42 + iteration)  # deterministic permutation
        perm = rng.permutation(n)

        for start in range(0, n, block_size):
            idx = perm[start:start + block_size]
            if len(idx) < 2:
                continue

            parity_alice = alice[idx].sum() % 2
            parity_bob = bob_corrected[idx].sum() % 2
            leaked_parity_bits += 1

            if parity_alice != parity_bob:
                low, high = 0, len(idx) - 1
                while low < high:
                    mid = (low + high) // 2
                    sub_idx = idx[low:mid+1]
                    sub_parity_alice = alice[sub_idx].sum() % 2
                    sub_parity_bob = bob_corrected[sub_idx].sum() % 2
                    leaked_parity_bits += 1

                    if sub_parity_alice != sub_parity_bob:
                        high = mid
                    else:
                        low = mid + 1

                err_pos = idx[low]
                bob_corrected[err_pos] ^= 1
                errors_corrected += 1

    return bob_corrected.tolist(), errors_corrected, leaked_parity_bits


# -----------------------------------------------------------------------------
# PRIVACY AMPLIFICATION (UNIVERSAL HASHING)
# -----------------------------------------------------------------------------
def privacy_amplification(bits: list, final_key_length: int, auth_key: bytes = b"") -> list:
    """
    Apply a random universal hash function (matrix multiplication over GF(2))
    to reduce the key to final_key_length bits.
    """
    n = len(bits)
    if final_key_length >= n:
        raise ValueError("final_key_length must be smaller than input length")

    rng = np.random.default_rng(int.from_bytes(auth_key[:4], 'big') % (2**32))
    matrix = rng.integers(0, 2, size=(final_key_length, n), dtype=np.uint8)

    bits_array = np.array(bits, dtype=np.uint8).reshape(-1, 1)
    hashed = (matrix @ bits_array) % 2
    return hashed.flatten().tolist()


# -----------------------------------------------------------------------------
# MAIN SIMULATION CLASS
# -----------------------------------------------------------------------------
class BB84Simulation:
    def __init__(
        self,
        num_qubits: int,
        eve_prob: float = 0.0,
        depolarising_noise: float = 0.0,
        sacrifice_pct: float = 0.20,
        threshold: float = 0.11,
        seed: int = 42,
        enable_error_correction: bool = True,
        enable_privacy_amplification: bool = True,
        enable_authentication: bool = True
    ):
        self.num_qubits = num_qubits
        self.eve_prob = eve_prob
        self.depolarising_noise = depolarising_noise
        self.sacrifice_pct = sacrifice_pct
        self.threshold = threshold
        self.seed = seed
        self.enable_ec = enable_error_correction
        self.enable_pa = enable_privacy_amplification
        self.enable_auth = enable_authentication

        self.auth_key = hashlib.sha256(str(seed).encode()).digest() if enable_auth else b""
        np.random.seed(seed)

        self.alice = Alice(num_qubits)
        self.eve = Eve(eve_prob)
        self.bob = Bob(num_qubits)

    def run(self):
        sent_states = self.alice.encode()
        channel_states = self.eve.attack(sent_states)
        bob_results = self.bob.measure(channel_states, self.depolarising_noise)

        sifted_indices = [
            i for i in range(self.num_qubits)
            if self.alice.bases[i] == self.bob.bases[i]
        ]
        sifted_len = len(sifted_indices)

        if sifted_len == 0:
            return self._abort("No bases matched during reconciliation.")

        num_sacrifice = max(1, int(sifted_len * self.sacrifice_pct))
        sacrifice_indices = np.random.choice(sifted_indices, size=num_sacrifice, replace=False)
        errors = sum(
            1 for i in sacrifice_indices
            if self.alice.bits[i] != self.bob.results[i]
        )
        qber = errors / num_sacrifice

        if qber >= self.threshold:
            return self._abort(f"QBER {qber:.2%} ≥ threshold {self.threshold:.2%}")

        remaining_indices = [i for i in sifted_indices if i not in sacrifice_indices]
        alice_raw = [self.alice.bits[i] for i in remaining_indices]
        bob_raw = [self.bob.results[i] for i in remaining_indices]

        if self.enable_ec and len(alice_raw) > 0:
            bob_corrected, ec_errors, parity_leaked = binary_error_correction(
                alice_raw, bob_raw,
                block_size=8,
                max_iterations=5,
                auth_key=self.auth_key
            )
        else:
            bob_corrected = bob_raw
            ec_errors = 0
            parity_leaked = 0

        if self.enable_pa and len(alice_raw) > 0:
            final_len = max(1, int((1 - qber - 0.05) * len(alice_raw)))
            alice_final = privacy_amplification(alice_raw, final_len, self.auth_key)
            bob_final = privacy_amplification(bob_corrected, final_len, self.auth_key)
        else:
            final_len = len(alice_raw)
            alice_final = alice_raw
            bob_final = bob_corrected

        keys_match = (alice_final == bob_final)

        alice_key_str = "".join(map(str, alice_final))
        bob_key_str = "".join(map(str, bob_final))
        alice_hash = hashlib.sha256(alice_key_str.encode()).hexdigest()[:16] if alice_key_str else "N/A"
        bob_hash = hashlib.sha256(bob_key_str.encode()).hexdigest()[:16] if bob_key_str else "N/A"

        auth_log = []
        if self.enable_auth:
            alice_bases_msg = "".join(self.alice.bases)
            bob_bases_msg = "".join(self.bob.bases)
            alice_bases_tag = hmac_sha256(self.auth_key, "Alice_bases:" + alice_bases_msg)
            bob_bases_tag = hmac_sha256(self.auth_key, "Bob_bases:" + bob_bases_msg)
            auth_log.append(("Alice's basis announcement", alice_bases_tag[:16]))
            auth_log.append(("Bob's basis announcement", bob_bases_tag[:16]))

            if self.enable_ec:
                parity_msg = f"Parity info (leaked {parity_leaked} bits)"
                parity_tag = hmac_sha256(self.auth_key, parity_msg)
                auth_log.append(("Error correction parity exchange", parity_tag[:16]))

            if self.enable_pa:
                pa_msg = f"PA matrix (final length {final_len})"
                pa_tag = hmac_sha256(self.auth_key, pa_msg)
                auth_log.append(("Privacy amplification matrix", pa_tag[:16]))

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
            "sifted_indices": sifted_indices,
            "sacrifice_indices": list(sacrifice_indices),
            "remaining_indices": remaining_indices,
            "auth_log": auth_log,
            "alice_raw": "".join(map(str, alice_raw)),
            "bob_raw": "".join(map(str, bob_raw)),
            "bob_corrected": "".join(map(str, bob_corrected)),
            "alice_final": alice_key_str,
            "bob_final": bob_key_str,
        }

    def _abort(self, reason: str):
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
            "sifted_indices": [],
            "sacrifice_indices": [],
            "remaining_indices": [],
            "auth_log": [],
            "alice_raw": "",
            "bob_raw": "",
            "bob_corrected": "",
            "alice_final": "",
            "bob_final": "",
        }


# -----------------------------------------------------------------------------
# UI CODE (Light theme)
# -----------------------------------------------------------------------------
st.title("⚛️ BB84 Quantum Key Distribution Simulator")
st.markdown("""
This simulator demonstrates the BB84 protocol, including quantum transmission,  
eavesdropping, basis reconciliation, error correction, and privacy amplification.
""")

st.sidebar.header("⚙️ Simulation Parameters")

seed = st.sidebar.number_input(
    "Random Seed",
    min_value=0,
    value=42,
    step=1,
    help="Set a seed for reproducible experiments."
)

total_qubits = st.sidebar.slider(
    "Total Transmitted Qubits (N)",
    min_value=20,
    max_value=300,
    value=100,
    step=10,
    help="Number of polarised photons Alice sends."
)

eve_active = st.sidebar.checkbox("Enable Eavesdropper (Eve)", value=True)
eve_prob = 0.0
if eve_active:
    eve_prob = st.sidebar.slider(
        "Eve Interception Probability",
        min_value=0.1,
        max_value=1.0,
        value=1.0,
        step=0.1,
        help="Probability that Eve intercepts each photon."
    )

depolarising_noise = st.sidebar.slider(
    "Depolarising Noise (p)",
    min_value=0.0,
    max_value=0.20,
    value=0.02,
    step=0.01,
    help="Probability that a photon is replaced by a completely mixed state before Bob's measurement."
)

abort_threshold = st.sidebar.slider(
    "Abort Threshold (QBER)",
    min_value=0.05,
    max_value=0.25,
    value=0.11,
    step=0.01,
    help="If estimated QBER ≥ threshold, protocol aborts."
)

sacrifice_ratio = st.sidebar.slider(
    "Sacrifice Ratio",
    min_value=0.10,
    max_value=0.40,
    value=0.20,
    step=0.05,
    help="Fraction of sifted bits used for QBER estimation."
)

st.sidebar.subheader("Advanced Options")
enable_ec = st.sidebar.checkbox("Enable Error Correction", value=True)
enable_pa = st.sidebar.checkbox("Enable Privacy Amplification", value=True)
enable_auth = st.sidebar.checkbox("Enable Authenticated Classical Channel", value=True)

sim = BB84Simulation(
    num_qubits=total_qubits,
    eve_prob=eve_prob,
    depolarising_noise=depolarising_noise,
    sacrifice_pct=sacrifice_ratio,
    threshold=abort_threshold,
    seed=seed,
    enable_error_correction=enable_ec,
    enable_privacy_amplification=enable_pa,
    enable_authentication=enable_auth
)
results = sim.run()

# -----------------------------------------------------------------------------
# DASHBOARD METRICS
# -----------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Sifted Bits", f"{results['sifted_len']} bits")
with col2:
    st.metric("Estimated QBER", f"{results['qber']:.2%}")
with col3:
    status = "ACCEPTED ✅" if not results["aborted"] else "ABORTED ❌"
    st.metric("Protocol Status", status)
with col4:
    if results["aborted"]:
        match = "DISCARDED ⚠️"
    else:
        match = "MATCH ✅" if results["keys_match"] else "MISMATCH ❌"
    st.metric("Final Key Match", match)

if results["aborted"]:
    st.error(f"🚨 **Protocol Aborted:** {results['reason']}")
else:
    st.success(
        f"🎉 **Protocol Accepted** – QBER {results['qber']:.2%} is below threshold. "
        f"Final key length: **{results['final_len']} bits**."
    )

# -----------------------------------------------------------------------------
# TABS
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Analysis",
    "🔍 Qubit Ledger",
    "🔐 Key Distillation",
    "🔬 Security Log"
])

# ----- Tab 1: Analysis -----
with tab1:
    st.subheader("Channel Statistics")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))
    # Light background for figures
    fig.patch.set_facecolor('white')

    labels = ['QBER Test', 'Final Key (after EC/PA)', 'Basis Mismatch', 'Raw (post‑sift, pre‑EC)']
    sizes = [
        results['sacrifice_len'],
        results['final_len'],
        total_qubits - results['sifted_len'],
        results['remaining_raw_len'] - results['final_len']
    ]
    colors = ['#FFC107', '#00B4D8', '#D3D3D3', '#90A4AE']

    wedges, _, _ = ax1.pie(
        sizes,
        labels=None,
        autopct='%1.1f%%',
        startangle=140,
        colors=colors,
        pctdistance=0.8,
        textprops=dict(color="black", fontsize=10)
    )
    ax1.legend(
        wedges,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncol=2,
        frameon=False,
        fontsize=10
    )
    ax1.set_title("Photon Utilisation", color='black', pad=15)

    bars = ax2.bar(['Estimated QBER', 'Abort Threshold'],
                   [results['qber']*100, abort_threshold*100],
                   color=['#FF4B4B' if results['qber'] >= abort_threshold else '#00B4D8', '#D3D3D3'])
    ax2.set_ylabel("Error Rate (%)", color='black')
    ax2.set_title("QBER vs Threshold", color='black', pad=15)
    ax2.tick_params(colors='black')
    for bar in bars:
        height = bar.get_height()
        ax2.annotate(f'{height:.2f}%', xy=(bar.get_x()+bar.get_width()/2, height),
                     xytext=(0,3), textcoords="offset points", ha='center', color='black')

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    colA, colB, colC = st.columns(3)
    colA.metric("Errors Corrected (EC)", results['ec_errors_corrected'])
    colB.metric("Parity Bits Leaked (EC)", results['parity_leaked'])
    colC.metric("Final Key Rate", f"{results['final_len']/total_qubits:.3f} bits/qubit")

# ----- Tab 2: Qubit Ledger -----
with tab2:
    st.subheader("Qubit‑by‑Qubit Technical Log")
    pol_symbols = {0.0: "↑ (0°)", 90.0: "→ (90°)", 45.0: "↗ (45°)", 135.0: "↖ (135°)"}
    records = []
    for i in range(total_qubits):
        if sim.alice.bases[i] == 'Z':
            state = 0.0 if sim.alice.bits[i] == 0 else 90.0
        else:
            state = 45.0 if sim.alice.bits[i] == 0 else 135.0

        eve_b = sim.eve.bases[i] if eve_active else '-'
        eve_r = sim.eve.results[i] if (eve_active and sim.eve.results[i] != -1) else '-'
        match = "YES" if sim.alice.bases[i] == sim.bob.bases[i] else "NO"
        records.append({
            "Index": i,
            "Alice Bit": sim.alice.bits[i],
            "Alice Basis": sim.alice.bases[i],
            "Alice State": pol_symbols.get(state, f"{state}°"),
            "Eve Basis": eve_b,
            "Eve Result": eve_r,
            "Bob Basis": sim.bob.bases[i],
            "Bob Result": sim.bob.results[i],
            "Bases Match": match
        })
    df = pd.DataFrame(records)
    def style_row(row):
        if row["Bases Match"] == "YES":
            return ["background-color: #E3F2FD; color: #000000"]*len(row)
        return ["background-color: #FFFFFF; color: #666666"]*len(row)
    st.dataframe(df.style.apply(style_row, axis=1), use_container_width=True, height=450)

# ----- Tab 3: Key Distillation -----
with tab3:
    st.subheader("Key Distillation Pipeline")
    if results["aborted"]:
        st.warning("Protocol aborted – no key generated.")
    else:
        st.markdown("**Step 1 – Sifted Raw Key (after basis reconciliation)**")
        c1, c2 = st.columns(2)
        c1.text_area("Alice Raw", results["alice_raw"], height=80, disabled=True)
        c2.text_area("Bob Raw", results["bob_raw"], height=80, disabled=True)

        if enable_ec:
            st.markdown("**Step 2 – After Error Correction**")
            c1, c2 = st.columns(2)
            c1.text_area("Alice Corrected", results["alice_raw"], height=80, disabled=True)
            c2.text_area("Bob Corrected", results["bob_corrected"], height=80, disabled=True)

        if enable_pa:
            st.markdown("**Step 3 – Final Key (after Privacy Amplification)**")
            c1, c2 = st.columns(2)
            c1.text_area("Alice Final Key", results["alice_final"], height=80, disabled=True)
            c2.text_area("Bob Final Key", results["bob_final"], height=80, disabled=True)

        st.markdown("**Integrity Check (SHA‑256)**")
        c1, c2 = st.columns(2)
        c1.code(f"Alice: {results['alice_hash']}")
        c2.code(f"Bob:   {results['bob_hash']}")

        if results["keys_match"]:
            st.success("Final keys are identical.")
        else:
            st.error("Final keys do NOT match (should not happen after EC).")

        st.info(
            "SHA‑256 is used only as a consistency check. "
            "Authentication is provided by the HMAC layer shown in the Security Log."
        )

# ----- Tab 4: Security Log -----
with tab4:
    st.subheader("Authenticated Public Communication (HMAC‑SHA256)")
    if not enable_auth:
        st.info("Authentication is disabled. Public messages are unprotected.")
    else:
        st.markdown("Below are simulated authentication tags for public messages.")
        for msg, tag in results["auth_log"]:
            st.write(f"**{msg}** → tag: `{tag}...`")
        st.success(
            "All public discussions (basis announcement, parity exchange, PA matrix) "
            "are authenticated with a pre‑shared secret, preventing tampering."
        )

    st.markdown("---")
    st.subheader("Security Parameters")
    st.markdown(f"""
    - **QBER estimate:** {results['qber']:.2%}
    - **Sacrifice bits:** {results['sacrifice_len']}
    - **Parity bits leaked during EC:** {results['parity_leaked']}
    - **Final key length after PA:** {results['final_len']} bits
    """)
    st.markdown(
        "The simulation includes simplified error correction and privacy amplification. "
        "Real QKD systems use more advanced protocols and rigorous security proofs."
    )

# Footer
st.markdown("---")
st.markdown(
    "⚛️ **BB84 Quantum Key Distribution Simulator** – explore the protocol step by step."
)
