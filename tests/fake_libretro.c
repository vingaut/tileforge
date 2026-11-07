/*
 * Cœur libretro factice pour les tests de TileForge.
 *
 * Il n'émule rien : il expose une RAM système, une VRAM et une SRAM de tailles
 * connues, y écrit un motif déterministe à chaque trame, et renvoie une image
 * de 4 × 2 pixels. Il sert à vérifier l'hôte libretro sans dépendre d'un vrai
 * émulateur.
 *
 * Compilation :
 *   gcc -shared -fPIC -O2 -o fake_libretro.so tests/fake_libretro.c
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define RAM_SIZE 65536
#define VRAM_SIZE 32768
#define SRAM_SIZE 8192

struct retro_system_info {
    const char *library_name;
    const char *library_version;
    const char *valid_extensions;
    bool need_fullpath;
    bool block_extract;
};

struct retro_game_info {
    const char *path;
    const void *data;
    size_t size;
    const char *meta;
};

typedef bool (*retro_environment_t)(unsigned cmd, void *data);
typedef void (*retro_video_refresh_t)(const void *data, unsigned width,
                                      unsigned height, size_t pitch);
typedef void (*retro_audio_sample_t)(int16_t left, int16_t right);
typedef size_t (*retro_audio_sample_batch_t)(const int16_t *data, size_t frames);
typedef void (*retro_input_poll_t)(void);
typedef int16_t (*retro_input_state_t)(unsigned port, unsigned device,
                                       unsigned index, unsigned id);

static retro_environment_t environ_cb;
static retro_video_refresh_t video_cb;
static retro_audio_sample_t audio_cb;
static retro_audio_sample_batch_t audio_batch_cb;
static retro_input_poll_t input_poll_cb;
static retro_input_state_t input_state_cb;

static uint8_t ram[RAM_SIZE];
static uint8_t vram[VRAM_SIZE];
static uint8_t sram[SRAM_SIZE];
static uint16_t picture[8] = {
    0xF800, 0x07E0, 0x001F, 0xFFFF,
    0x0000, 0x8410, 0xFC00, 0x03E0,
};
static unsigned frames;
static bool loaded;
static uint16_t buttons_seen;

unsigned retro_api_version(void) { return 1; }

void retro_set_environment(retro_environment_t cb) { environ_cb = cb; }
void retro_set_video_refresh(retro_video_refresh_t cb) { video_cb = cb; }
void retro_set_audio_sample(retro_audio_sample_t cb) { audio_cb = cb; }
void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb) { audio_batch_cb = cb; }
void retro_set_input_poll(retro_input_poll_t cb) { input_poll_cb = cb; }
void retro_set_input_state(retro_input_state_t cb) { input_state_cb = cb; }

void retro_get_system_info(struct retro_system_info *info) {
    info->library_name = "Fake Core";
    info->library_version = "1.0";
    info->valid_extensions = "bin|rom";
    info->need_fullpath = false;
    info->block_extract = false;
}

void retro_init(void) {
    memset(ram, 0, sizeof(ram));
    memset(vram, 0, sizeof(vram));
    memset(sram, 0, sizeof(sram));
    frames = 0;
    buttons_seen = 0;
    loaded = false;
    if (environ_cb) {
        unsigned format = 2;                 /* RGB565 */
        environ_cb(10, &format);
    }
}

void retro_deinit(void) { loaded = false; }

bool retro_load_game(const struct retro_game_info *info) {
    if (!info || !info->data || info->size == 0)
        return false;
    loaded = true;
    frames = 0;
    if (environ_cb) {
        const char *directory = NULL;
        if (!environ_cb(9, &directory) || !directory)
            return false;
        bool dupe = false;
        environ_cb(3, &dupe);
    }
    return true;
}

void retro_unload_game(void) { loaded = false; }

void retro_run(void) {
    if (!loaded)
        return;
    frames += 1;
    if (input_poll_cb && input_state_cb) {
        input_poll_cb();
        buttons_seen |= (uint16_t) input_state_cb(0, 1, 0, 256);
    }
    /* Compteur de trames sur deux octets, puis un motif de tuiles. */
    ram[0] = (uint8_t) (frames & 0xFF);
    ram[1] = (uint8_t) ((frames >> 8) & 0xFF);
    ram[2] = (uint8_t) (buttons_seen & 0xFF);
    ram[3] = (uint8_t) ((buttons_seen >> 8) & 0xFF);
    for (int i = 0; i < 4096; i++)
        ram[0x1000 + i] = (uint8_t) ((i * 13 + 7) & 0xFF);
    vram[0] = 0xA5;
    vram[1] = (uint8_t) (frames & 0xFF);
    sram[0] = 0x5A;
    if (video_cb)
        video_cb(picture, 4, 2, 4 * sizeof(uint16_t));
    if (audio_batch_cb)
        audio_batch_cb(NULL, 0);
    else if (audio_cb)
        audio_cb(0, 0);
}

void *retro_get_memory_data(unsigned id) {
    if (id == 2) return ram;
    if (id == 3) return vram;
    if (id == 0) return sram;
    return NULL;
}

size_t retro_get_memory_size(unsigned id) {
    if (id == 2) return RAM_SIZE;
    if (id == 3) return VRAM_SIZE;
    if (id == 0) return SRAM_SIZE;
    return 0;
}

void retro_reset(void) { frames = 0; }

size_t retro_serialize_size(void) { return 0; }
bool retro_serialize(void *data, size_t size) { (void) data; (void) size; return false; }
bool retro_unserialize(const void *data, size_t size) { (void) data; (void) size; return false; }

void retro_set_controller_port_device(unsigned port, unsigned device) {
    (void) port;
    (void) device;
}

unsigned retro_get_region(void) { return 0; }
