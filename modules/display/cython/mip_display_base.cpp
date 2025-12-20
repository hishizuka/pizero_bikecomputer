#include "mip_display_base.hpp"


void MipDisplayBase::init_common() {
  status_quit.store(false, std::memory_order_relaxed);

  gpio_write_value(GPIO_DISP, true);
  gpio_write_value(GPIO_VCOMSEL, true);
  usleep(6);

  clear();
  set_brightness(0);
  usleep(6);

  threads_.push_back(std::thread(&MipDisplayBase::draw_worker, this));
}

void MipDisplayBase::quit() {
  {
    std::unique_lock<std::mutex> ul(mutex_);
    if(status_quit.load(std::memory_order_acquire)) {
      return;
    }
    status_quit.store(true, std::memory_order_release);
  } //release lock
  cv_.notify_all();
  for(unsigned int i = 0; i < threads_.size(); i++) {
    if(threads_.at(i).joinable()) {
      threads_.at(i).join();
    }
  }
  threads_.clear();

  // Ensure no concurrent update() is accessing buffers or backend while we tear down.
  {
    std::lock_guard<std::mutex> guard(update_mutex_);

    clear();
    set_brightness(0);
    gpio_write_value(GPIO_DISP, false); //OFF
    usleep(100000);

    close_backend();

    if(buf_image != nullptr) {
      delete[] buf_image;
      buf_image = nullptr;
    }
    if(pre_buf_image != nullptr) {
      delete[] pre_buf_image;
      pre_buf_image = nullptr;
    }
  }
}

void MipDisplayBase::set_screen_size(int w, int h, int c) {
  WIDTH = w;
  HEIGHT = h;
  COLORS = c;

  if(COLORS == 2) {
    BPP = 1;
    BUF_WIDTH = WIDTH*BPP/8 + 2;
    conv_color = &MipDisplayBase::conv_1bit_2colors;
  }
  else if(COLORS == 8) {
    BPP = 3;
    BUF_WIDTH = WIDTH*BPP/8 + 2;
    //conv_color = &MipDisplayBase::conv_3bit_8colors;
    conv_color = &MipDisplayBase::conv_3bit_27colors;
  }
  else if(COLORS == 64) {
    BPP = 6;
    BUF_WIDTH = WIDTH*BPP/8 + 4;
    HALF_BUF_WIDTH_64COLORS = WIDTH*BPP/8/2;
    //conv_color = &MipDisplayBase::conv_4bit_64colors;
    conv_color = &MipDisplayBase::conv_4bit_343colors;
  }
  int length = HEIGHT*BUF_WIDTH;

  if(buf_image != nullptr) {
    delete[] buf_image;
    buf_image = nullptr;
  }
  if(pre_buf_image != nullptr) {
    delete[] pre_buf_image;
    pre_buf_image = nullptr;
  }

  buf_image = new char[length];
  pre_buf_image = new char[length];

  // SPI transfers are limited by the underlying driver/user-space interface.
  // We always append 2 footer bytes (0x00, 0x00) to end an update.
  SPI_MAX_ROWS = int((SPI_MAX_BUF_SIZE - 2) / BUF_WIDTH);
  if(SPI_MAX_ROWS < 1) {
    SPI_MAX_ROWS = 1;
  }

  clear_buf();
  memcpy(pre_buf_image, buf_image, length);
}

void MipDisplayBase::clear_buf() {
  memset(buf_image, 0, HEIGHT*BUF_WIDTH);
  for(int i = 0; i < HEIGHT; i++) {
    buf_image[i*BUF_WIDTH] = UPDATE_MODE + (i >> 8);
    buf_image[i*BUF_WIDTH+1] = (char)((unsigned int)i);

/*
 * The following code is adapted from an Apache License 2.0 project.
 * Copyright (c) Azumo 2024
 * 
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     third-party/apache/LICENSE.Apache2
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * 
 * start
 */
    if(COLORS == 64) {
      buf_image[i*BUF_WIDTH] |= 0b10;
      buf_image[i*BUF_WIDTH+2+HALF_BUF_WIDTH_64COLORS] = (i >> 8);
      buf_image[i*BUF_WIDTH+2+HALF_BUF_WIDTH_64COLORS+1] = (char)((unsigned int)i);
    }
  /* end */
  }
}

void MipDisplayBase::clear() {
  spi_write_bytes(buf_clear, 2);
}

void MipDisplayBase::no_update() {
  spi_write_bytes(buf_no_update, 2);
}

void MipDisplayBase::set_PWM(int b) {
  set_PWM_duty(b);
}

void MipDisplayBase::set_brightness(int brightness) {
  if(pre_brightness == brightness) {
    return;
  }

  int b = brightness;
  if(b >= 100) {
    b = 100;
  } else if (b <= 0) {
    b = 0;
  }
  set_PWM(b);
  pre_brightness = b;
  usleep(50000);
}

void MipDisplayBase::inversion(float sec) {
  float s = sec;
  bool state = true;

  while(s > 0) {
    if(
      (COLORS == 64 && WIDTH == 272 && HEIGHT == 451)
    ){
      int l1 = BUF_WIDTH * int(HEIGHT/2);
      int l2 = BUF_WIDTH*HEIGHT - l1;
      std::vector<char> buf1(l1 + 2), buf2(l2 + 2);

      // copy the buffer
      memcpy(buf1.data(), pre_buf_image, l1);
      memcpy(buf2.data(), pre_buf_image + l1, l2);
      // fill footer
      buf1[l1] = 0;
      buf1[l1 + 1] = 0;
      buf2[l2] = 0;
      buf2[l2 + 1] = 0;

      // Invert the buffer if state is true
      if(state) {
        int b, x, y, i;
        int y_ends[2] = {int(HEIGHT/2), HEIGHT - int(HEIGHT/2)};
        int skip_byte[2] = {2 + HALF_BUF_WIDTH_64COLORS, 2 + HALF_BUF_WIDTH_64COLORS + 1};
        char* bufs[2] = {buf1.data(), buf2.data()};

        for(b = 0; b < 2; b++) {
          for(y = 0; y < y_ends[b]; y++){
            for(x = 2; x < BUF_WIDTH; x++){
              if(x == skip_byte[0] || x == skip_byte[1]) {
                continue;
              }
              i = y * BUF_WIDTH + x;
              bufs[b][i] = ~bufs[b][i];
            }
          }
        }
      }

      spi_write_bytes(buf1.data(), buf1.size());
      spi_write_bytes(buf2.data(), buf2.size());
    }
    else {
      if(state) {
        spi_write_bytes(buf_inversion, 2);
      }
      else {
        spi_write_bytes(buf_no_update, 2);
      }
    }
    usleep(inversion_interval*1000000);
    s -= inversion_interval;
    state = !state;
  }
  spi_write_bytes(buf_no_update, 2);
}

void MipDisplayBase::draw_worker() {
  while (1) {
    std::vector<char> q;
    {
      std::unique_lock<std::mutex> ul(mutex_);
      while (queue_.empty()) {
        if (get_status_quit()) { return; }
        cv_.wait(ul);
      }
      q = std::move(queue_.front());
      queue_.pop();
    } //release
    draw(q);
  }
}

bool MipDisplayBase::get_status_quit() {
  return status_quit.load(std::memory_order_acquire);
}

void MipDisplayBase::update(unsigned char* image) {
  std::lock_guard<std::mutex> guard(update_mutex_);
  if(get_status_quit()) {
    return;
  }
  if(buf_image == nullptr || pre_buf_image == nullptr || conv_color == nullptr) {
    return;
  }

  clear_buf();
  int update_lines = (this->*conv_color)(image);

  if(update_lines == 0) {
    return;
  }

  // Build transfer buffers without holding the queue lock to minimize contention.
  // The updated rows are packed from the start of buf_image by conv_color().
  const int max_rows_per_xfer = SPI_MAX_ROWS;
  int remaining_rows = update_lines;
  int byte_offset = 0;
  std::vector<std::vector<char> > bufs;
  bufs.reserve((remaining_rows + max_rows_per_xfer - 1) / max_rows_per_xfer);

  while(remaining_rows > 0) {
    const int rows = std::min(remaining_rows, max_rows_per_xfer);
    const int payload_bytes = BUF_WIDTH * rows;
    std::vector<char> buf(payload_bytes + 2);
    memcpy(buf.data(), buf_image + byte_offset, payload_bytes);
    buf[payload_bytes] = 0;
    buf[payload_bytes + 1] = 0;
    bufs.emplace_back(std::move(buf));

    byte_offset += payload_bytes;
    remaining_rows -= rows;
  }

  {
    std::unique_lock<std::mutex> ul(mutex_);
    for(auto &buf : bufs) {
      queue_.emplace(std::move(buf));
    }
  } //release lock
  cv_.notify_all();
}

int MipDisplayBase::conv_1bit_2colors(unsigned char* image) {
  int update_lines = 0;
  (void)image;
  return update_lines;
}

int MipDisplayBase::conv_3bit_8colors(unsigned char* image) {

  unsigned char *image_index = image;
  char *buf_image_index = buf_image;
  char b0, b1, b2, b3, b4, b5, b6, b7;

  char *buf_image_diff_index = buf_image;
  char *pre_buf_image_diff_index = pre_buf_image;
  char *buf_image_update_index = buf_image;
  int update_lines = 0;

  int width_24byte = int(WIDTH*3/24);

  for(int y = 0; y < HEIGHT; y++) {
    buf_image_index += 2;
    for(int x = 0; x < width_24byte; x++) {
      b0 = *image_index++;
      b1 = *image_index++;
      b2 = *image_index++;
      b3 = *image_index++;
      b4 = *image_index++;
      b5 = *image_index++;
      b6 = *image_index++;
      b7 = *image_index++;
      *buf_image_index++ = 
        (b0 & 0b10000000) |
        ((b1 & 0b10000000) >> 1) |
        ((b2 & 0b10000000) >> 2) |
        ((b3 & 0b10000000) >> 3) |
        ((b4 & 0b10000000) >> 4) |
        ((b5 & 0b10000000) >> 5) |
        ((b6 & 0b10000000) >> 6) |
        ((b7 & 0b10000000) >> 7);

      b0 = *image_index++;
      b1 = *image_index++;
      b2 = *image_index++;
      b3 = *image_index++;
      b4 = *image_index++;
      b5 = *image_index++;
      b6 = *image_index++;
      b7 = *image_index++;
      *buf_image_index++ = 
        (b0 & 0b10000000) |
        ((b1 & 0b10000000) >> 1) |
        ((b2 & 0b10000000) >> 2) |
        ((b3 & 0b10000000) >> 3) |
        ((b4 & 0b10000000) >> 4) |
        ((b5 & 0b10000000) >> 5) |
        ((b6 & 0b10000000) >> 6) |
        ((b7 & 0b10000000) >> 7);

      b0 = *image_index++;
      b1 = *image_index++;
      b2 = *image_index++;
      b3 = *image_index++;
      b4 = *image_index++;
      b5 = *image_index++;
      b6 = *image_index++;
      b7 = *image_index++;
      *buf_image_index++ = 
        (b0 & 0b10000000) |
        ((b1 & 0b10000000) >> 1) |
        ((b2 & 0b10000000) >> 2) |
        ((b3 & 0b10000000) >> 3) |
        ((b4 & 0b10000000) >> 4) |
        ((b5 & 0b10000000) >> 5) |
        ((b6 & 0b10000000) >> 6) |
        ((b7 & 0b10000000) >> 7);
    }

    if(memcmp(buf_image_diff_index, pre_buf_image_diff_index, BUF_WIDTH) != 0) {
      memcpy(pre_buf_image_diff_index, buf_image_diff_index, BUF_WIDTH);
      memcpy(buf_image_update_index, pre_buf_image_diff_index, BUF_WIDTH);
      update_lines++;
      buf_image_update_index += BUF_WIDTH;
    }
    buf_image_diff_index += BUF_WIDTH;
    pre_buf_image_diff_index += BUF_WIDTH;
  }
  return update_lines;
}

int MipDisplayBase::conv_3bit_27colors(unsigned char* image) {

  unsigned char *image_index = image;
  char *buf_image_index = buf_image;

  char *buf_image_diff_index = buf_image;
  char *pre_buf_image_diff_index = pre_buf_image;
  char *buf_image_update_index = buf_image;
  int update_lines = 0;

  bool t_index = true;
  int bit_count;

  for(int y = 0; y < HEIGHT; y++) {
    buf_image_index += 2;
    bit_count = 0;

    //3bit color CPU code
    for(int x = 0; x < WIDTH; x++) {
      if(*image_index++ >= thresholds_3bit_27colors[t_index]) {
        *buf_image_index |= add_bit[bit_count];
      }
      bit_count = (bit_count+1)&7;
      buf_image_index += 1 - (bool)bit_count;

      if(*image_index++ >= thresholds_3bit_27colors[t_index]) {
        *buf_image_index |= add_bit[bit_count];
      }
      bit_count = (bit_count+1)&7;
      buf_image_index += 1 - (bool)bit_count;

      if(*image_index++ >= thresholds_3bit_27colors[t_index]) {
        *buf_image_index |= add_bit[bit_count];
      }
      bit_count = (bit_count+1)&7;
      buf_image_index += 1 - (bool)bit_count;

      t_index = !t_index;
    }
    t_index = !t_index;

    // diff check and update_lines
    if(memcmp(buf_image_diff_index, pre_buf_image_diff_index, BUF_WIDTH) != 0) {
      memcpy(pre_buf_image_diff_index, buf_image_diff_index, BUF_WIDTH);
      memcpy(buf_image_update_index, pre_buf_image_diff_index, BUF_WIDTH);
      update_lines++;
      buf_image_update_index += BUF_WIDTH;
    }
    buf_image_diff_index += BUF_WIDTH;
    pre_buf_image_diff_index += BUF_WIDTH;
  }

  return update_lines;
}

int MipDisplayBase::conv_4bit_64colors(unsigned char* image) {

  unsigned char *image_index = image;
  char *buf_image_index = buf_image;
  char *buf_image_index_high = buf_image;
  char b0, b1, b2, b3, b4, b5, b6, b7;

  char *buf_image_diff_index = buf_image;
  char *pre_buf_image_diff_index = pre_buf_image;
  char *buf_image_update_index = buf_image;
  int update_lines = 0;

  int width_24byte = int(WIDTH*3/24);

  //riemersma_dithering(image);

  buf_image_index += 2;      
  buf_image_index_high += 2 + HALF_BUF_WIDTH_64COLORS + 2;
  for(int y = 0; y < HEIGHT; y++) {
    for(int x = 0; x < width_24byte; x++) {
      b0 = *image_index++;
      b1 = *image_index++;
      b2 = *image_index++;
      b3 = *image_index++;
      b4 = *image_index++;
      b5 = *image_index++;
      b6 = *image_index++;
      b7 = *image_index++;
      *buf_image_index++ = 
        ((b0 & 0b01000000) << 1) |
        (b1 & 0b01000000) |
        ((b2 & 0b01000000) >> 1) |
        ((b3 & 0b01000000) >> 2) |
        ((b4 & 0b01000000) >> 3) |
        ((b5 & 0b01000000) >> 4) |
        ((b6 & 0b01000000) >> 5) |
        ((b7 & 0b01000000) >> 6);
      *buf_image_index_high++ =
        (b0 & 0b10000000) |
        ((b1 & 0b10000000) >> 1) |
        ((b2 & 0b10000000) >> 2) |
        ((b3 & 0b10000000) >> 3) |
        ((b4 & 0b10000000) >> 4) |
        ((b5 & 0b10000000) >> 5) |
        ((b6 & 0b10000000) >> 6) |
        ((b7 & 0b10000000) >> 7);
      
      b0 = *image_index++;
      b1 = *image_index++;
      b2 = *image_index++;
      b3 = *image_index++;
      b4 = *image_index++;
      b5 = *image_index++;
      b6 = *image_index++;
      b7 = *image_index++;
      *buf_image_index++ = 
        ((b0 & 0b01000000) << 1) |
        (b1 & 0b01000000) |
        ((b2 & 0b01000000) >> 1) |
        ((b3 & 0b01000000) >> 2) |
        ((b4 & 0b01000000) >> 3) |
        ((b5 & 0b01000000) >> 4) |
        ((b6 & 0b01000000) >> 5) |
        ((b7 & 0b01000000) >> 6);
      *buf_image_index_high++ =
        (b0 & 0b10000000) |
        ((b1 & 0b10000000) >> 1) |
        ((b2 & 0b10000000) >> 2) |
        ((b3 & 0b10000000) >> 3) |
        ((b4 & 0b10000000) >> 4) |
        ((b5 & 0b10000000) >> 5) |
        ((b6 & 0b10000000) >> 6) |
        ((b7 & 0b10000000) >> 7);

      b0 = *image_index++;
      b1 = *image_index++;
      b2 = *image_index++;
      b3 = *image_index++;
      b4 = *image_index++;
      b5 = *image_index++;
      b6 = *image_index++;
      b7 = *image_index++;
      *buf_image_index++ = 
        ((b0 & 0b01000000) << 1) |
        (b1 & 0b01000000) |
        ((b2 & 0b01000000) >> 1) |
        ((b3 & 0b01000000) >> 2) |
        ((b4 & 0b01000000) >> 3) |
        ((b5 & 0b01000000) >> 4) |
        ((b6 & 0b01000000) >> 5) |
        ((b7 & 0b01000000) >> 6);
      *buf_image_index_high++ =
        (b0 & 0b10000000) |
        ((b1 & 0b10000000) >> 1) |
        ((b2 & 0b10000000) >> 2) |
        ((b3 & 0b10000000) >> 3) |
        ((b4 & 0b10000000) >> 4) |
        ((b5 & 0b10000000) >> 5) |
        ((b6 & 0b10000000) >> 6) |
        ((b7 & 0b10000000) >> 7);
    }
  
    // next start
    buf_image_index += 2 + HALF_BUF_WIDTH_64COLORS + 2;
    buf_image_index_high += 2 + HALF_BUF_WIDTH_64COLORS + 2;
    
    if(memcmp(buf_image_diff_index, pre_buf_image_diff_index, BUF_WIDTH) != 0) {
      memcpy(pre_buf_image_diff_index, buf_image_diff_index, BUF_WIDTH);
      memcpy(buf_image_update_index, pre_buf_image_diff_index, BUF_WIDTH);
      update_lines++;
      buf_image_update_index += BUF_WIDTH;
    }
    buf_image_diff_index += BUF_WIDTH;
    pre_buf_image_diff_index += BUF_WIDTH;
  }
  return update_lines;
}

int MipDisplayBase::conv_4bit_343colors(unsigned char* image) {

  unsigned char *image_index = image;
  char *buf_image_index = buf_image;
  char *buf_image_index_high = buf_image;

  char *buf_image_diff_index = buf_image;
  char *pre_buf_image_diff_index = pre_buf_image;
  char *buf_image_update_index = buf_image;
  int update_lines = 0;

  bool t_index = true;
  int bit_count;

  buf_image_index += 2;
  buf_image_index_high += 2 + HALF_BUF_WIDTH_64COLORS + 2;
  for(int y = 0; y < HEIGHT; y++) {
    bit_count = 0;

    for(int x = 0; x < WIDTH; x++) {
      for(int i = 0; i < 3; i++) {
        if(*image_index >= thresholds_4bit_343colors[t_index][1]) {
          *buf_image_index_high |= add_bit[bit_count];
        }
        if(
          *image_index >= thresholds_4bit_343colors[t_index][2] ||
          (*image_index >= thresholds_4bit_343colors[t_index][0] && *image_index < thresholds_4bit_343colors[t_index][1])
        ) {
          *buf_image_index |= add_bit[bit_count];
        }
        bit_count = (bit_count+1)&7;
        buf_image_index += 1 - (bool)bit_count;
        buf_image_index_high += 1 - (bool)bit_count;
        image_index++;
      }
      t_index = !t_index;
    }
    t_index = !t_index;

    // next start
    buf_image_index += 2 + HALF_BUF_WIDTH_64COLORS + 2;
    buf_image_index_high += 2 + HALF_BUF_WIDTH_64COLORS + 2;

    if(memcmp(buf_image_diff_index, pre_buf_image_diff_index, BUF_WIDTH) != 0) {
      memcpy(pre_buf_image_diff_index, buf_image_diff_index, BUF_WIDTH);
      memcpy(buf_image_update_index, pre_buf_image_diff_index, BUF_WIDTH);
      update_lines++;
      buf_image_update_index += BUF_WIDTH;
    }
    buf_image_diff_index += BUF_WIDTH;
    pre_buf_image_diff_index += BUF_WIDTH;
  }
  return update_lines;
}

void MipDisplayBase::draw(std::vector<char>& buf_queue) {
  spi_write_bytes(buf_queue.data(), buf_queue.size());
}
