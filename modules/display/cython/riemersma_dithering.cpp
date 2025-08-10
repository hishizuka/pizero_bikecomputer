// https://www.compuphase.com/riemer.c

#include <cstring>
#include <math.h>

#include "mip_display.hpp"

#define R_SIZE 16
#define R_MAX 16
#define R_MASK (R_SIZE - 1)
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define CLAMP8(x) ((x) < 0 ? 0 : ((x) > 255 ? 255 : (x)))

enum {
  NONE,
  UP,
  LEFT,
  DOWN,
  RIGHT,
};


void MipDisplay::init_weights() {
  double m = exp(log(R_MAX) / (R_SIZE - 1));
  double v = 1.0;
  for (int i = 0; i < R_SIZE; i++) {
    weights[i] = (int)(v + 0.5);
    v *= m;
  }
  for (int i = 0; i < 256; i++)
    quantize_lut[i] = color_4_levels[(i + 42) / 85 < 4 ? (i + 42) / 85 : 3];
}

int MipDisplay::quantize_4level(int value)
{
  int best = 0;
  int min_diff = 1e9;
  for (int i = 1; i < 4; i++) {
    int diff = abs(value - color_4_levels[i]);
    if (diff < min_diff) {
      best = i;
      min_diff = diff;
    }
  }
  return color_4_levels[best];
}

void MipDisplay::dither_pixel_rgb(unsigned char *pixel) {
  int i, pval, err;

  // R
  err = 0;
  for (i = 0; i < R_SIZE; i++) err += error_r[i] * weights[i];
  pval = pixel[0] + err / R_MAX;
  pval = (pval >= 128) ? 255 : 0;
  memmove(error_r, error_r + 1, (R_SIZE - 1) * sizeof(int));
  error_r[R_SIZE - 1] = pixel[0] - pval;
  pixel[0] = (unsigned char)pval;

  // G
  err = 0;
  for (i = 0; i < R_SIZE; i++) err += error_g[i] * weights[i];
  pval = pixel[1] + err / R_MAX;
  pval = (pval >= 128) ? 255 : 0;
  memmove(error_g, error_g + 1, (R_SIZE - 1) * sizeof(int));
  error_g[R_SIZE - 1] = pixel[1] - pval;
  pixel[1] = (unsigned char)pval;

  // B
  err = 0;
  for (i = 0; i < R_SIZE; i++) err += error_b[i] * weights[i];
  pval = pixel[2] + err / R_MAX;
  pval = (pval >= 128) ? 255 : 0;
  memmove(error_b, error_b + 1, (R_SIZE - 1) * sizeof(int));
  error_b[R_SIZE - 1] = pixel[2] - pval;
  pixel[2] = (unsigned char)pval;
}

void MipDisplay::dither_pixel_rgb_64(unsigned char *pixel) {
  int i, pval, err;

  // R
  err = 0;
  for (i = 0; i < R_SIZE; i++) err += error_r[i] * weights[i];
  pval = pixel[0] + err / R_MAX;
  //pval = quantize_4level(pval);
  pval = quantize_lut[CLAMP8(int(pval))];
  memmove(error_r, error_r + 1, (R_SIZE - 1) * sizeof(int));
  error_r[R_SIZE - 1] = pixel[0] - pval;
  pixel[0] = (unsigned char)pval;

  // G
  err = 0;
  for (i = 0; i < R_SIZE; i++) err += error_g[i] * weights[i];
  pval = pixel[1] + err / R_MAX;
  //pval = quantize_4level(pval);
  pval = quantize_lut[CLAMP8(int(pval))];
  memmove(error_g, error_g + 1, (R_SIZE - 1) * sizeof(int));
  error_g[R_SIZE - 1] = pixel[1] - pval;
  pixel[1] = (unsigned char)pval;

  // B
  err = 0;
  for (i = 0; i < R_SIZE; i++) err += error_b[i] * weights[i];
  pval = pixel[2] + err / R_MAX;
  //pval = quantize_4level(pval);
  pval = quantize_lut[CLAMP8(int(pval))];
  memmove(error_b, error_b + 1, (R_SIZE - 1) * sizeof(int));
  error_b[R_SIZE - 1] = pixel[2] - pval;
  pixel[2] = (unsigned char)pval;
}

void MipDisplay::move(int direction) {
  if (cur_x >= 0 && cur_x < WIDTH && cur_y >= 0 && cur_y < HEIGHT)
    //dither_pixel_rgb(img_ptr);
    dither_pixel_rgb_64(img_ptr);

  switch (direction) {
    case LEFT:
      cur_x--;
      img_ptr -= 3;
      break;
    case RIGHT:
      cur_x++;
      img_ptr += 3;
      break;
    case UP:
      cur_y--;
      img_ptr -= WIDTH * 3;
      break;
    case DOWN:
      cur_y++;
      img_ptr += WIDTH * 3;
      break;
  }
}

void MipDisplay::hilbert_level(int level, int direction) {
  if (level == 1) {
    switch (direction) {
      case LEFT:  move(RIGHT); move(DOWN); move(LEFT); break;
      case RIGHT: move(LEFT); move(UP);   move(RIGHT); break;
      case UP:    move(DOWN); move(RIGHT);move(UP);    break;
      case DOWN:  move(UP);   move(LEFT); move(DOWN);  break;
    }
  } else {
    switch (direction) {
      case LEFT:
        hilbert_level(level - 1, UP);
        move(RIGHT);
        hilbert_level(level - 1, LEFT);
        move(DOWN);
        hilbert_level(level - 1, LEFT);
        move(LEFT);
        hilbert_level(level - 1, DOWN);
        break;
      case RIGHT:
        hilbert_level(level - 1, DOWN);
        move(LEFT);
        hilbert_level(level - 1, RIGHT);
        move(UP);
        hilbert_level(level - 1, RIGHT);
        move(RIGHT);
        hilbert_level(level - 1, UP);
        break;
      case UP:
        hilbert_level(level - 1, LEFT);
        move(DOWN);
        hilbert_level(level - 1, UP);
        move(RIGHT);
        hilbert_level(level - 1, UP);
        move(UP);
        hilbert_level(level - 1, RIGHT);
        break;
      case DOWN:
        hilbert_level(level - 1, RIGHT);
        move(UP);
        hilbert_level(level - 1, DOWN);
        move(LEFT);
        hilbert_level(level - 1, DOWN);
        move(DOWN);
        hilbert_level(level - 1, LEFT);
        break;
    }
  }
}

int MipDisplay::log2int(int value)
{
  int result = 0;
  while (value > 1) {
    value >>= 1;
    result++;
  }
  return result;
}

void MipDisplay::riemersma_dithering(unsigned char *image) {
  int level;
  int size = MAX(WIDTH, HEIGHT);
  memset(error_r, 0, sizeof(error_r));
  memset(error_g, 0, sizeof(error_g));
  memset(error_b, 0, sizeof(error_b));
  error_index = 0;

  level = log2int(size);
  if ((1 << level) < size)
    level++;

  img_ptr = image;
  cur_x = 0;
  cur_y = 0;

  if (level > 0)
    hilbert_level(level, UP);

  move(NONE);
}
