import os
import argparse
import numpy as np
import torch
from tensorboardX import SummaryWriter

from svhn import SVHN
from utils import *

parser = argparse.ArgumentParser()
parser.add_argument('--iters', type=int, default=int(1e5+1))
parser.add_argument('--schedule', type=int, nargs='+', default=[int(4e4), int(6e4)])
parser.add_argument('--batchsize', type=int, default=1000)
parser.add_argument('--lr', type=float, default=0.1)
parser.add_argument('--ghostsize', type=int, default=100)
parser.add_argument('--numghost', type=int, default=100)
parser.add_argument('--update-noise', type=int, default=10)
parser.add_argument('--momentum', type=float, default=0.0)
parser.add_argument('--weightdecay', type=float, default=0.0)
parser.add_argument('--model', type=str, default='vgg')
parser.add_argument('--resume', type=str, default=None)
parser.add_argument('--datadir', type=str, default='MultiNoise-master/SVHN/train25k_test70k')
parser.add_argument('--logdir', type=str, default='MultiNoise-master/SVHN/logs/GLD_Fisher')

args = parser.parse_args()
logger = LogSaver(args.logdir)
logger.save(str(args), 'args')

# data
dataset = SVHN(args.datadir)
logger.save(str(dataset), 'dataset')
train_list = dataset.getTrainList(args.batchsize, True)
test_list = dataset.getTestList(1000, True)

# model
start_iter = 0
lr = args.lr
if args.model == 'resnet':
    from resnet import ResNet18
    model = ResNet18().cuda()
elif args.model == 'vgg':
    from vgg import vgg11
    model = vgg11().cuda()
else:
    raise NotImplementedError()
criterion = torch.nn.CrossEntropyLoss().cuda()
optimizer = torch.optim.SGD(model.parameters(), lr=lr, momentum=args.momentum, weight_decay=args.weightdecay)
if args.resume:
    checkpoint = torch.load(args.resume)
    start_iter = checkpoint['iter'] + 1
    lr = checkpoint['lr']
    model.load_state_dict(checkpoint['model'])
    optimizer.load_state_dict(checkpoint['optimizer'])
    logger.save("=> loaded checkpoint '{}'".format(args.resume))
logger.save(str(model), 'classifier')
logger.save(str(optimizer), 'optimizer')

# writer
writer = SummaryWriter(args.logdir)

# get number of total param
n_param = 0
for name, param in model.named_parameters():
    n_param += len(param.view(-1))
logger.save(str(n_param), 'n_param')

torch.backends.cudnn.benchmark = True
for i in range(start_iter, args.iters):
    # decay lr
    if i in args.schedule:
        lr *= 0.1
        logger.save('update lr: %f'%(lr))
        for param_group in optimizer.param_groups:
            param_group['lr'] = lr

    # eval noise
    if i % args.update_noise == 0:
        eval_list = dataset.getTrainBatchList(args.ghostsize, args.numghost, True)
        diagF_dict, diag2 = evalFisherDiag(eval_list, model, criterion, optimizer)

    resume_noise = True if args.resume is not None else False
    if resume_noise:
        eval_list = dataset.getTrainBatchList(args.ghostsize, args.numghost, True)
        diagF_dict, diag2 = evalFisherDiag(eval_list, model, criterion, optimizer)
        resume_noise = False

    # train
    model.train()
    optimizer.zero_grad()
    train_loss, train_acc = 0, 0
    for x,y in train_list:
        out = model(x)
        loss = criterion(out, y)
        loss.backward()
        train_acc += accuracy(out, y).item()
        train_loss += loss.item()
    for name, param in model.named_parameters():
        param.grad.data /= len(train_list)
        param.grad.data += torch.randn(param.size()).cuda() * diagF_dict[name].sqrt()
    optimizer.step()
    train_acc /= len(train_list)
    train_loss /= len(train_list)

    # evaluate
    if i % 100 == 0 or i <= 100:
        model.eval()
        writer.add_scalar('lr', lr, i)
        writer.add_scalar('noise/norm2', diag2, i)
        writer.add_scalar('acc/train', train_acc, i)
        writer.add_scalar('loss/train', train_loss, i)

        test_loss, test_acc = 0, 0
        for x,y in test_list:
            out = model(x)
            test_loss += criterion(out, y).item()
            test_acc += accuracy(out, y).item()
        test_loss /= len(test_list)
        test_acc /= len(test_list)
        writer.add_scalar('loss/test', test_loss, i)
        writer.add_scalar('acc/test', test_acc, i)
        writer.add_scalar('acc/diff', train_acc - test_acc, i)

        logger.save('Iter:%d, Test [acc: %.2f, loss: %.4f], Train [acc: %.2f, loss: %.4f]' \
                % (i, test_acc, test_loss, train_acc, train_loss))

    if i % 2000 == 0:
        state = {'iter':i, 'lr':lr, 'model':model.state_dict(), 'optimizer':optimizer.state_dict()}
        torch.save(state, args.logdir+'/iter-'+str(i)+'.pth.tar')

writer.close()
