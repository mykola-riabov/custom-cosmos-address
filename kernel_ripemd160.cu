#include <stdint.h>

// Left rotation
__device__ uint32_t rotl(uint32_t x, int n) {
    return (x << n) | (x >> (32 - n));
}

__device__ void ripemd160(const uint8_t *msg, uint8_t *digest) {
    uint32_t h0 = 0x67452301, h1 = 0xefcdab89, h2 = 0x98badcfe;
    uint32_t h3 = 0x10325476, h4 = 0xc3d2e1f0;

    uint8_t block[64] = {0};
    for (int i = 0; i < 32; i++) block[i] = msg[i];
    block[32] = 0x80;
    block[56] = 32 * 8;

    uint32_t X[16];
    for (int i = 0; i < 16; i++) {
        X[i] = (uint32_t)block[i*4] |
               ((uint32_t)block[i*4+1] << 8) |
               ((uint32_t)block[i*4+2] << 16) |
               ((uint32_t)block[i*4+3] << 24);
    }

    uint32_t A = h0, B = h1, C = h2, D = h3, E = h4;
    uint32_t AA = h0, BB = h1, CC = h2, DD = h3, EE = h4;

    const int r1[80] = {
         0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10,11,12,13,14,15,
         7, 4,13, 1,10, 6,15, 3,12, 0, 9, 5, 2,14,11, 8,
         3,10,14, 4, 9,15, 8, 1, 2, 7, 0, 6,13,11, 5,12,
         1, 9,11,10, 0, 8,12, 4,13, 3, 7,15,14, 5, 6, 2,
         4, 0, 5, 9, 7,12, 2,10,14, 1, 3, 8,11, 6,15,13
    };
    const int r2[80] = {
         5,14, 7, 0, 9, 2,11, 4,13, 6,15, 8, 1,10, 3,12,
         6,11, 3, 7, 0,13, 5,10,14,15, 8,12, 4, 9, 1, 2,
        15, 5, 1, 3, 7,14, 6, 9,11, 8,12, 2,10, 0,13, 4,
         8, 6, 4, 1, 3,11,15, 0, 5,12, 2,13, 9, 7,10,14,
        12,15,10, 4, 1, 5, 8, 7, 6, 2,13,14, 0, 3, 9,11
    };
    const int s1[80] = {
        11,14,15,12, 5, 8, 7, 9,11,13,14,15, 6, 7, 9, 8,
         7, 6, 8,13,11, 9, 7,15, 7,12,15, 9,11, 7,13,12,
        11,13, 6, 7,14, 9,13,15,14, 8,13, 6, 5,12, 7, 5,
        11,12,14,15,14,15, 9, 8, 9,14, 5, 6, 8, 6, 5,12,
         9,15, 5,11, 6, 8,13,12, 5,12,13,14,11, 8, 5, 6
    };
    const int s2[80] = {
         8, 9, 9,11,13,15,15, 5, 7, 7, 8,11,14,14,12, 6,
         9,13,15, 7,12, 8, 9,11, 7, 7,12, 7, 6,15,13,11,
         9, 7,15,11, 8, 6, 6,14,12,13, 5,14,13,13, 7, 5,
        15, 5, 8,11,14,14, 6,14, 6, 9,12, 9,12, 5,15, 8,
         8, 5,12, 9,12, 5,14, 6, 8,13, 6, 5,15,13,11,11
    };
    const uint32_t K1[5] = {0x00000000,0x5a827999,0x6ed9eba1,0x8f1bbcdc,0xa953fd4e};
    const uint32_t K2[5] = {0x50a28be6,0x5c4dd124,0x6d703ef3,0x7a6d76e9,0x00000000};

    for (int j = 0; j < 80; j++) {
        int round = j / 16;
        uint32_t f = (round == 0) ? (B ^ C ^ D) :
                     (round == 1) ? ((B & C) | (~B & D)) :
                     (round == 2) ? ((B | ~C) ^ D) :
                     (round == 3) ? ((B & D) | (C & ~D)) :
                                    (B ^ (C | ~D));

        uint32_t T = rotl(A + f + X[r1[j]] + K1[round], s1[j]) + E;
        A = E; E = D; D = rotl(C, 10); C = B; B = T;

        f = (round == 0) ? (BB ^ (CC | ~DD)) :
            (round == 1) ? ((BB & DD) | (CC & ~DD)) :
            (round == 2) ? ((BB | ~CC) ^ DD) :
            (round == 3) ? ((BB & CC) | (~BB & DD)) :
                           (BB ^ CC ^ DD);

        T = rotl(AA + f + X[r2[j]] + K2[round], s2[j]) + EE;
        AA = EE; EE = DD; DD = rotl(CC, 10); CC = BB; BB = T;
    }

    uint32_t tmp = h1 + C + DD;
    h1 = h2 + D + EE;
    h2 = h3 + E + AA;
    h3 = h4 + A + BB;
    h4 = h0 + B + CC;
    h0 = tmp;

    digest[ 0] = h0 & 0xff;   digest[ 1] = (h0 >> 8) & 0xff;
    digest[ 2] = (h0 >> 16) & 0xff; digest[ 3] = (h0 >> 24) & 0xff;
    digest[ 4] = h1 & 0xff;   digest[ 5] = (h1 >> 8) & 0xff;
    digest[ 6] = (h1 >> 16) & 0xff; digest[ 7] = (h1 >> 24) & 0xff;
    digest[ 8] = h2 & 0xff;   digest[ 9] = (h2 >> 8) & 0xff;
    digest[10] = (h2 >> 16) & 0xff; digest[11] = (h2 >> 24) & 0xff;
    digest[12] = h3 & 0xff;   digest[13] = (h3 >> 8) & 0xff;
    digest[14] = (h3 >> 16) & 0xff; digest[15] = (h3 >> 24) & 0xff;
    digest[16] = h4 & 0xff;   digest[17] = (h4 >> 8) & 0xff;
    digest[18] = (h4 >> 16) & 0xff; digest[19] = (h4 >> 24) & 0xff;
}

extern "C" __global__ void ripemd160_gpu(const uint8_t *sha256_hashes, uint8_t *ripemd160_out, int count) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= count) return;
    ripemd160(&sha256_hashes[idx * 32], &ripemd160_out[idx * 20]);
}

