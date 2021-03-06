import pandas as pd
import numpy as np
from pathlib import Path
import os
from tqdm.notebook import tqdm
import torch
import torch.optim as optim
from torch.utils.data import Dataset
import torch.nn as nn
from torch.nn import functional
import zipfile
from torchvision import transforms
import numpy as np
from skimage.transform import rotate
# from sklearn.model_selection import KFold
import collections
from torch.optim.lr_scheduler import ReduceLROnPlateau
# from sklearn.utils import resample

data_folder = Path('/home/adkugusheva/brats_slices/')
df = pd.read_csv('/home/adkugusheva/exp_1/meta.csv', index_col=0)

from train import train_step
from augmentations import random_crop, random_rotate, normalize, to_tensor
from BratsDatasetClass import BraTSDataset
from MobileNet import MobileNetv2
from binary_acc import binary_acc
from train import train_step

train_transform = transforms.Compose([
                    random_crop,
                    random_rotate,
                    normalize,
                    to_tensor
            ])
val_transform = transforms.Compose([
                    normalize,
                    to_tensor
            ])

subj_id = list(set(df['subject_id']))
train_size = int(len(subj_id) * 0.8)

np.random.seed(0)
train_index = np.random.choice(subj_id, train_size, replace = False)
val_index = list(set(subj_id) - set(train_index))

train_df = df[df['subject_id'].isin(train_index)]
val_df = df[df['subject_id'].isin(val_index)]

train_dataset = BraTSDataset(train_df, data_folder, transform=train_transform)
val_dataset = BraTSDataset(val_df, data_folder, transform=val_transform)
train_loader = torch.utils.data.DataLoader(train_dataset,
                                             batch_size=64, shuffle=True,
                                             num_workers=1)
val_loader = torch.utils.data.DataLoader(val_dataset,
                                             batch_size=64, shuffle=False,
                                             num_workers=1)

device = ('cuda' if torch.cuda.is_available() else 'cpu')
criterion = nn.BCEWithLogitsLoss()
model = MobileNetv2().to(device).float()
optimizer = optim.Adam(model.parameters(), lr=0.001)
scheduler = ReduceLROnPlateau(optimizer, mode='max', factor=0.1, patience=2, verbose=True)
n_epochs = 50
stats = {'epoch': [], 'train_loss': [], 'val_loss': [], 'acc': []}
val_loss_min = np.Inf
for epoch in range(n_epochs):
    batch_train_loss = []
    epoch_loss = 0
    stats['epoch'].append(epoch)
    for images, labels in train_loader:
        loss = train_step(images, labels, model, criterion, optimizer)      
        epoch_loss += loss.item() 
        batch_train_loss.append(loss.item())
    stats['train_loss'].append(batch_train_loss)
    print(f'Epoch {epoch+0:03}: | Train Loss: {epoch_loss/len(train_loader):.5f}')

    model.eval()
    with torch.no_grad():
        batch_val_loss = []
        batch_acc = []
        epoch_val_loss = 0
        epoch_acc = 0
        for images, labels in val_loader:
            images, labels = images.to(device).float(), labels.to(device).float()
            outputs = model(images)
            val_loss = criterion(outputs, labels)
            epoch_val_loss += val_loss.item()
            acc = binary_acc(outputs, labels)
            epoch_acc += acc
            batch_acc.append(acc)
            batch_val_loss.append(val_loss.item())
        mean_acc = epoch_acc / len(val_loader)
        scheduler.step(mean_acc)
        stats['acc'].append(batch_acc)
        stats['val_loss'].append(batch_val_loss)
        # mean_val_loss = sum(stats['val_loss'][epoch])/len(stats['val_loss'][epoch])
        print('Test loss: {}'.format(epoch_val_loss / len(val_loader)))
        print('Accuracy: {} %'.format(mean_acc))
        np.save('/home/adkugusheva/exp_24/stats.npy', stats)
        if epoch_val_loss < val_loss_min:
            torch.save(model.state_dict(), '/home/adkugusheva/exp_24/model_'+str(epoch)+'.pt')
            val_loss_min = epoch_val_loss
            print('Saving model...')