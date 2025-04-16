#include <stdint.h>
#include <curand_kernel.h>

// Rotate right
__device__ __forceinline__ uint32_t rotr(uint32_t x, int n) {
    return (x >> n) | (x << (32 - n));
}

// Minimal SHA256: compresses 32-byte input
__device__ void sha256_simple(const uint8_t *input, uint8_t *out) {
    const uint32_t k[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,
        0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,
        0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,
        0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,
        0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,
        0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,
        0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,
        0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,
        0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
    };

    uint32_t h[8] = {
        0x6a09e667, 0xbb67ae85,
        0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c,
        0x1f83d9ab, 0x5be0cd19
    };

    uint8_t block[64] = {0};
    for (int i = 0; i < 32; i++) block[i] = input[i];
    block[32] = 0x80;
    block[63] = 32 * 8;

    uint32_t w[64];
    for (int i = 0; i < 16; i++) {
        w[i] = (block[i*4] << 24) | (block[i*4+1] << 16) | (block[i*4+2] << 8) | block[i*4+3];
    }
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = rotr(w[i-15], 7) ^ rotr(w[i-15],18) ^ (w[i-15] >> 3);
        uint32_t s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }

    uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],h_=h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = rotr(e,6)^rotr(e,11)^rotr(e,25);
        uint32_t ch = (e&f)^((~e)&g);
        uint32_t temp1 = h_ + S1 + ch + k[i] + w[i];
        uint32_t S0 = rotr(a,2)^rotr(a,13)^rotr(a,22);
        uint32_t maj = (a&b)^(a&c)^(b&c);
        uint32_t temp2 = S0 + maj;
        h_ = g; g = f; f = e;
        e = d + temp1;
        d = c; c = b; b = a;
        a = temp1 + temp2;
    }

    h[0] += a; h[1] += b; h[2] += c; h[3] += d;
    h[4] += e; h[5] += f; h[6] += g; h[7] += h_;

    for (int i = 0; i < 8; i++) {
        out[i*4+0] = (h[i] >> 24) & 0xff;
        out[i*4+1] = (h[i] >> 16) & 0xff;
        out[i*4+2] = (h[i] >> 8) & 0xff;
        out[i*4+3] = h[i] & 0xff;
    }
}

// GPU kernel: privkey + SHA256 on GPU
extern "C" __global__ void generate_keys(uint8_t *privkeys, uint8_t *hashes, int batch, unsigned int seed_offset) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= batch) return;

    int offset = idx * 32;
    unsigned int seed = clock64() + idx + seed_offset;
    curandState state;
    curand_init(seed, 0, 0, &state);

    for (int i = 0; i < 32; ++i) {
        privkeys[offset + i] = curand(&state) & 0xFF;
    }

    sha256_simple(&privkeys[offset], &hashes[offset]);
}

